# FLEx Modeling Decisions -- Which Construct for Which Situation

[Back to README](../README.md) | Used by [Stage 07](../stages/07-allomorphy-modeling.md)

This is the **most generalizable content in the corpus**: the recurring question
"which FLEx construct models this linguistic situation?", answered from what the
project actually tried, including what it tried and abandoned.

Nothing here is Malayalam-specific. The examples are Malayalam, the logic is not.

---

## 1. The decision table

Read the **Conditioning** column first. Getting the conditioning type wrong is the
root of both of the corpus's largest rework cycles.

| # | Linguistic situation | Conditioning | Use this FLEx construct | Do NOT use | Evidence |
|---|---|---|---|---|---|
| 1 | One invariant form | none | Plain lexeme form only | anything else | -- |
| 2 | Two or more surface shapes, choice predictable from the **adjacent segments** | phonological, local | **Plain allomorph + phonological environment** on `PhoneEnvRC`; lexeme form left as the elsewhere case | affix-process rule (too heavy); inflection class (wrong dimension) | D-M3-05, L-M3-13 |
| 3 | Same as #2, and the conditioning set recurs across 4+ allomorphs | phonological, shared | Same, but factor the set into a **named natural class** and reference it in the environment | repeating the literal set | D-M3-05 |
| 4 | Same as #2, but the conditioning is **local to one lexical subclass** | phonological, but scoped | **Literal (non-shared) environment** + a dedicated **inflection class** | extending a shared natural class | D-M5-14, C-M5-05 |
| 5 | The elsewhere form itself over-applies | -- | Constrain the **lexeme form** with an environment too | leaving it free | D-M3-06, L-M3-14 |
| 6 | Choice predictable from an **arbitrary lexical subclass** of stems (a conjugation / declension) | lexical | **`MoInflClass`** on the POS; assign stems via their stem MSA; restrict competing allomorphs via the allomorph's inflection-class collection | phonological environment (there is no phonological generalization to state) | D-M1-08, L-M3-10, L-M3-12, L-M8-01 |
| 7 | Choice predictable from a **semantic/grammatical property** of the stem (animacy, humanness) | lexical/semantic | Same as #6 -- an inflection class is the vehicle for any non-phonological stem subclass | a natural class (natural classes are phonological) | D-M1-08, L-M1-05 |
| 8 | Stem alternates by the **grammatical features being realized** (tense, aspect), not by sound | grammatical | **`MoStemName`** on the alternate, keyed to a feature-system region, **plus matching inflection features on the consuming affix's MSA** | a right-context phonological environment | **D-M4-03, L-M4-03, L-M4-04** |
| 9 | As #8, **and** the stem needs different **inflection-class** behavior per allomorph | grammatical + lexical | **Split the alternate into its own `LexEntry` as a variant** (a "Past"-type variant), with its own sense and MSA carrying the class; strip the class from the base; delete the now-redundant stem-named allomorph | relying on the stem's MSA class (it is allomorph-**global**) | **D-M8-05, D-M8-06, D-M8-07** |
| 10 | An **unpredictable suppletive stem** used across a set of paradigm cells | lexical, suppletive | **Variant entry** (`LexEntryRef`) with a purpose-built variant type | an allomorph (no conditioning to state) | D-M5-03, L-M5-03 |
| 11 | A **whole irregular inflected word** filling a specific inflection slot | grammatical, irregular | **`LexEntryInflType`** (an inflection variant) that **fills the relevant slot**, under "Irregularly Inflected Form" | a plain variant type -- it does not fill a slot | **D-M5-04, L-M5-04** |
| 12 | **Non-concatenative** allomorphy: the affix replaces, truncates, or rewrites part of the stem | phonological, non-concatenative | **`MoAffixProcess`**: a variable + natural-class context as input, copy-from-input and/or insert-phones as output, one ordered subrule per trigger class | a plain allomorph (cannot express replacement) | D-M1-09, L-M1-04, L-M2-01..05 |
| 13 | A **general** sound alternation holding across the lexicon in a stateable environment | phonological, general | **`PhRegularRule`** (a global phonological rule), boundary-anchored | storing the derived allomorph on every entry | D-M1-07, L-M1-01..03 |
| 14 | As #13, but the alternation should apply only to a lexical subset | phonological, gated | The same rule with **two scoped right-hand sides**, gated by a dedicated inflection class and a rule feature | duplicating the rule, or making it fully general | L-M7-03 |
| 15 | An **augment/linker** inserted between stem and inflection for a whole class of stems | morphological | An **inflectional affix in the relevant slot**, with affix-process allomorphs that strip the triggering segment | 92 separate variant entries (what it replaced) | L-M7-01 |
| 16 | A **category-changing** affix (nominalizer, participle-to-adverb) | derivational | **`MoDerivAffMsa`** with from-POS and to-POS; if it selects a specific stem form, carry the feature or class on the derivational MSA | **never** an inflectional template slot | **C-M6-03, L-M6-06, L-M8-05** |
| 17 | A **stem-forming compound** of two words | compounding | **Binary compound rule** with member categories and explicit headedness | listing the compound as an entry | L-M6-07 |
| 18 | A compound-only stem shape for a particular lexeme | lexical, compounding | A **per-lexeme compound-form allomorph** | a general phonological rule | L-M6-07 |
| 19 | A bound morpheme attaching **outside** the inflectional template | clitic | A separate **enclitic entry** with the attached citation form, attachment declared, plus allomorphs for boundary epenthesis | an inflectional slot filler | **D-M5-07**, L-M5-05 |
| 20 | A recurring bound morpheme across a closed class of whole-word entries | morphological | **Decompose**: base entry + productive clitic, and retire the whole-word entries -- but only the transparent ones, and only after the derivation is verified to parse | retiring an opaque form | **D-M5-09, D-M5-10, L-M5-07** |
| 21 | A spelling variant of the same morpheme | orthographic | Two **allomorphs on the same entry** | two entries | L-M8-03 |
| 22 | A form homographic with an unrelated existing entry | -- | A **separate homograph entry**; log the collision | reusing the unrelated entry | L-M6-05, D-M5-03 |
| 23 | A category whose members never inflect | -- | The POS owns **zero** templates and slots, **and inherits none**: a subcategory of a POS that owns a template with an obligatory slot fails as a free word, so make it top-level (or give it its own minimal template). Check the morph type too: a free word typed as bound stem fails | an empty template; a templateless subcategory under a templated parent | L-M2-10; **L-S9-01, L-S9-03, D-S9-03** -- *Swahili, parse-verified* |
| 24 | A bare stem that cannot surface as a word | morphotactic | Mark the relevant slot **non-optional** | optional (it will over-generate bare stems) | **D-M1-02** |
| 25 | **Noun class / gender that affixes and concord must agree with** (Bantu noun classes) | grammatical, agreement | **Closed inflection features** on the stem's MSA: the singular class plus the paired plural class, and `NA` in every inapplicable feature. Prefixes carry matching values in an obligatory ClassPrefix slot. Catalog-sourced features, nested under one complex feature (`noun agreement`) | an inflection class (it carries no agreement value for concord to match); leaving features unspecified (unification then cannot block anything) | **D-S1-06, D-S3-01, D-S4-05, V-S8-04** -- *Swahili*. By 09-25 the `NA` fill was gone; unification is by exact value (D-S8-11, V-S10-02) |
| 26 | A **zero morph** filling an obligatory slot (null class prefix) | morphological | An affix entry with form `∅`, `IsAbstract=False`, carrying feature values **on the same features the stems carry**. Give every stem that must take it (proper nouns too) a value it can unify with. Count the analyses it produces: null morphs are inserted freely and stack | an empty form (rejected); a placeholder grapheme; features disjoint from the stems' (it then matches everything); a null morph as a template's only anchor | **D-S2-01, L-S1-01, L-S4-01, L-S2-02, L-S9-04**; over-generation measured: V-S10-07 (*mwana* 13, *Misri* 10 analyses) -- *Swahili* |
| 27 | **Full reduplication** | morphological | Affix with form `[...]`, `IsAbstract=True`; as a **derivational** MSA (V -> V) once the derivational extensions left the template | listing reduplicated words | D-S2-02, V-S6-04 (Matthew: `[...]` is the correct syntax), S7 (made derivational) -- *Swahili, never parse-verified* |
| 28 | A **neutralized segment** whose surface value depends on context (a placeless nasal) | phonological | An **archiphoneme**: a phoneme marked by a custom `[+archi]` feature, `[-archi]` surface natural classes, and an alpha-feature rule that fills in the value | storing every assimilated allomorph | D-S1-03 -- *Swahili* |
| 29 | A slot is **obligatory in one construction and absent or optional in another** (TAM required with an object marker; no TAM in the subjunctive) | morphotactic | **Separate templates per construction.** Where only the optionality differs, **clone the slot** (TAM2) -- optionality lives on the shared slot object | making the shared slot optional (over-generates everywhere); "consolidating duplicate slots" without reading why they exist | **L-S5-02, L-S6-04, D-S6-08, L-S7-02**, contrast C-S2-02, C-S6-02, C-S7-02 -- *Swahili*. Optionality is a property of the **slot object**, not of its use in a template, which is why the clone is the only way |
| 30 | One affix appears in **more than one slot** | morphotactic | Reuse the MSA across slots **only if those slots never co-occur in any template** (Obj and its clone Obj2 share all 14 object-marker MSAs) | putting it in co-occurring slots (one form fills both: the two-subject parse) | **L-S5-01, D-S5-01, L-S7-02, V-S7-09** -- *Swahili* |
| 31 | A verb class predictable from an **existing lexical field** (citation `ku`+stem vs `ku`+stem+V marks final-vowel behaviour) | lexical | Inflection classes (row 6), **assigned by a rule over the lexicon's own field**, anomalies to a human. Roots stored without the fused final vowel. Root+FV entries are duplicates. Root+extension forms are decomposed (row 35) unless judged lexicalized | growing the class inventory one corpus failure at a time; listing root+FV stems; derived stems as environment-less allomorphs of the root (*zaa*: *zalia, zaliwa*) | **D-S5-04, L-S4-02, L-S10-04** -- *Swahili* |
| 32 | An affix form **homophonous across several agreement values** (one concord prefix serving classes 4, 6 and 9) | grammatical, agreement | **One sense per agreement value**, each with its own feature structure and slot. A gloss must not name more values than its features encode | one sense with a multi-value gloss over a one-value feature structure (the other values silently fail to unify); allomorphs or separate entries (this is feature variation, not form variation) | **D-S8-07, D-S8-08, L-S8-03** -- *Swahili* |
| 33 | Every template needs an **anchor** | morphotactic | At least one obligatory **overt** slot, or a bound-stem morph type on the stems that the template cannot match bare | a template whose slots are all optional, or whose only anchor is a null morpheme (it matches every stem) | **L-S7-03, L-S7-04** -- *Swahili* |
| 34 | A template's **slot fillers** | morphotactic | Filler MSAs whose POS is the template's POS **or an ancestor of it** | reusing MSAs owned by a sibling POS (the template is inert and never fires) | **L-S7-04** -- *Swahili* |
| 35 | **Valency-changing derivation** (causative, applicative, passive, stative, reciprocal) | derivational | `MoDerivAffMsa` between **POS subcategories** that encode valency (Verb > Underived > {Transitive, Intransitive}; Verb > Detransitive). Classify every stem first; prototype on a subset; convert atomically against a parse baseline. A subcategory inherits the parent's templates | inflectional template slots (row 16); stems that bake the extension in | **V-S7-01, L-S7-05, D-S7-05, D-S7-06**; relapses C-S7-06, C-S10-03 -- *Swahili, parse outcome not logged* |
| 36 | An affix that **changes an agreement value** already on the word (a locative suffix re-classing a noun) | derivational | `MoDerivAffMsa` Noun -> Noun with **ToInflFeats** | an inflectional MSA with the new value (inflectional features unify, they do not overwrite, so it fails against the stem's own class) | **L-S7-01** -- *Swahili, reasoned only, not implemented* |
| 37 | A **general** rule that must not apply to a lexical subset | phonological, lexically gated | An **exception feature** in the rule's excluded rule features, set on the exempt items (compare row 14). Count the parsed words that depend on the rule's output first. If the real conditioning is one morpheme (a prefix), put the restriction there, or move the alternation into that morpheme's allomorphs | disabling the rule (in S9 the disable never persisted); tagging every affected stem when one prefix is the trigger | **L-S10-02**, L-S9-06, V-S9-07 -- *Swahili, parse-verified* |

### 1b. Matthew's choice (Swahili)

Section 7's merge instruction asked for a "Matthew's choice" column. To keep the table
above readable it is given here, keyed by row number. Rows 25-37 above are new and
come from Matthew's project only. **Both rows are kept wherever the two practices
differ.** Source shards S1-S11, covering both machines' Swahili logs (to 2026-09-30).
Where a choice changed, the late state is given with the early one.

| Row | Matthew's choice | Agrees? | Evidence |
|---|---|---|---|
| 2 | S1: after merging allomorphs, the **lexeme form held the most-restricted form** with an environment, and no elsewhere form remained. **Retracted 09-12:** "the default/everywhere form of the affix should be the lexeme" -- 20 entries swapped by porting FieldWorks' `SwapAllomorphWithLexeme` (move owned objects, so stored analyses keep their references). Late prefix entries follow F1 and parse | **Yes (late).** The S1 arrangement is superseded, not a convention. [README 4.11](../README.md), Q-37 | L-S1-02 -> **D-S6-04, D-S6-05, L-S6-02, V-S6-01, V-S9-04, V-S10-04** |
| 2 (breadth) | An environment written as a natural class (`/ _ [V]`) blocked regular forms; narrowed to the attested segments (`/ _ a`, `/ _ e`) after listing the analyses that use the allomorph | Yes -- refines row 2 | L-S9-07, L-S10-06 |
| 3-4 | Feature-based classes; rebuilt segment-based Vowels/Consonants as feature-based through a referrer repoint | Yes | L-S1-03, D-S2-03 |
| 6-7 | Not used for noun class (row 25 instead). Used for verb final-vowel classes, assigned from the citation form (row 31) | Partly -- different language type | D-S5-04 |
| 13 | Started unanchored (and in one case context-free), then anchored every rule on "+". **Matthew's converse, 09-12:** "phonological rules are for very broad phenomena, but allomorphs and affix process rules are for morphophonemics specific to an affix." The glide rule kept one word-initial RHS with no POS limit and broke class-4 nouns until 09-25 | Yes (arrived at independently), plus the converse Ron never stated | C-S1-07, D-S2-03, **D-S6-07, L-S7-08, V-S9-07** |
| 14 | Lexical gating by an **exception feature** on the exempt stems, not by an inflection class + rule feature (row 37) | Partly -- different device for the same job; the real trigger (one prefix) arguably wants the restriction on the prefix | L-S10-02 |
| 16 | S1-S5: same mistake as Ron's M6, verb extensions in inflectional slots. **Fixed 09-13:** all six extensions became `MoDerivAffMsa` between valency subcategories (row 35); the empty slots were removed. Relapsed twice for one root (*zaa*) | **Yes (late)**, by repeating then correcting Ron's error | C-S1-06, C-S2-03, L-S3-01 -> **V-S7-01, L-S7-05**; C-S7-06, C-S10-03 |
| 20 | Decomposed demonstratives and the connective through templates; kept suppletive pronouns whole: "No parsing benefit." Whole-word possessives suppressed (not retired) only after the compositional parse was attested in the corpus -- with the deprecated `DoNotUseForParsing` flag (section 7) | Yes | D-S2-04, D-S7-04, D-S8-12 |
| 21 | Case variants: **upper-case graphemes** in the phoneme inventory, not capitalised allomorphs or entries | Adds a case Ron did not meet; confirmed 09-25 | D-S5-02, V-S10-09 |
| 22 | Homographs split **by function** (`ku-` infinitive vs negative past, in different slots). Later the infinitive became a second, verbal MSA on the cl.15 noun prefix | Yes, extended | L-S5-03, S7 |
| 23 | Free words failed because their POS **inherited** a template: Pronoun moved to top level, `amba-` given its own `Verb > Relativizer` POS + minimal template, invariant numerals a templateless top-level POS. About 3,000 tokens unblocked with no new entry | Yes, and refines the row ("inherits none") | L-S9-01, L-S9-02, L-S9-03 |
| 24 | First relaxed slots so forms would parse; later replaced by per-construction templates (row 29). Relapsed 09-13: TAM2 made optional for habitual / negative-present forms | Late practice agrees, with one relapse (open) | C-S2-02, L-S5-02, C-S7-02 |

---

## 2. The three facts that make the table make sense

These are FLEx/LCM architecture facts, not linguistic ones. Each was learned the hard
way in the corpus.

### F1. The lexeme form is the elsewhere case

FLEx orders the lexeme form **last**, under the negation of every environment above
it. So the correct pattern is: constrain the *alternates* with environments, and leave
the true elsewhere form as the lexeme form. The corpus had to swap a lexeme form with
its alternate to restore this ordering (L-M3-13).

Consequences:
- If your lexeme form over-applies, either the alternates' environments are too narrow,
  or the lexeme form itself needs constraining (#5).
- An environment **pre-empts the lexeme form even when the alternate's string does not
  match the surface** (L-M4-03). This is why a phonological environment cannot stand in
  for grammatical conditioning.

### F2. Inflection class on a stem's MSA is allomorph-global

`InflectionClassRA` is set on the MSA, and the MSA belongs to the *sense*, not to an
allomorph. Every allomorph of the entry therefore inherits it. Ron's own statement of
the consequence:

> "a non-past stem of a verb could get married with a NMLZ suffix or any past suffix
> and be seen as valid since the inflection class on the verb applies to all
> allomorphs. To mitigate this we could create a variant for past stems and add a sense
> to that stem so that we can put the right inflection class on the msa object."
> (D-M8-05)

This is why row #9 exists and why it beats row #8 alone.

A stem name (row #8) restricts **which affix can see which allomorph**. It does not
give per-allomorph class behavior. The two devices solve different halves of the
problem and the final architecture uses both.

### F3. Plain allomorphs and affix-process rules do not coexist on one entry

Plain alternates shadow the process rules (C-M1-06). Convert an entry's alternates
**uniformly** -- and then check the citation lexeme form is still reachable as a real,
parseable alternate, because converting the others can orphan it (C-M1-05, D-M1-11).

Related: two affix-process rules with the **same environment** cannot both fire on one
entry; that needs two entries (L-M3-04).

---

## 3. Choosing between the three "irregular form" constructs

These three look alike and are not interchangeable. The corpus distinguished them
explicitly (D-M5-04).

| | Plain variant type | Inflection variant type (`LexEntryInflType`) | Stem allomorph |
|---|---|---|---|
| What it is | A separate entry linked as a variant of a head | A separate entry linked as a variant **that fills an inflection slot** | An alternate form on the head entry |
| Fills a slot? | No | **Yes** -- names the slot and appends the gloss | No |
| Carries its own MSA/class? | Yes (it is an entry) | Yes | **No** -- shares the head's MSA (F2) |
| Conditioning | none stated | the slot it fills | phonological environment and/or stem name |
| Use for | Suppletive stems used across many cells (L-M5-03) | A whole irregular inflected word occupying one cell (L-M5-04) | Phonologically predictable alternation (#2) |
| Use for (added late) | **Per-allomorph inflection-class behavior** (#9, D-M8-05) | | |

**Watch for:** variant types are often **sub-possibilities** of "Irregularly Inflected
Form" and a flat search will not find them (C-M6-02). Always recurse.

---

## 4. Escalation ladder

Reach for the cheapest construct that expresses the conditioning. Escalate only on
proof that it cannot.

```
plain allomorph
   |  needs conditioning on adjacent segments
   v
+ phonological environment (literal)
   |  same set used by 4+ allomorphs
   v
+ named natural class in the environment
   |  conditioning is lexical, not phonological
   v
inflection class on the MSA + allomorph restriction
   |  conditioning is by realized grammatical features
   v
stem name + inflection features on the consuming affix
   |  the stem needs per-allomorph class behavior
   v
split the allomorph into its own variant entry with its own MSA
   |  the alternation is non-concatenative
   v
affix-process rule (uniformly, across the whole entry)
   |  the alternation is general across the lexicon
   v
global phonological rule (boundary-anchored), and delete the derived allomorphs
```

Two things constrain escalation in both directions:

- **Escalating costs maintainability and parse time.** A global rule with an unanchored
  context took the corpus's parse time to 9.6s on a single word (L-M3-02).
- **Under-escalating produces silent wrongness.** A phonological environment standing
  in for grammatical conditioning pre-empts the lexeme form and makes homophonous
  suffixes unparseable (L-M4-03).

---

## 5. Cross-cutting rules that apply whichever construct you pick

1. **Blast radius before edit.** Check referrers before touching a shared class,
   environment, or feature (C-M5-05).
2. **Enumerate before narrowing.** Before restricting a previously-unrestricted
   allomorph, list every class that legitimately needs it (C-M5-06).
3. **Intersect shape with category.** Before any bulk operation driven by an
   orthographic predicate, add a POS check (C-M7-01).
4. **Reuse, do not duplicate.** Look up the existing environment/class object rather
   than creating a second with the same string (D-M7-05).
5. **Proof of recipe, then siblings, then the class** (D-M1-09, D-M8-06, D-M8-07).
6. **Plan first, mutate second**, including inside LCM object graphs (D-M7-03,
   D-M7-04).
7. **Sibling interfaces on one object.** The same underlying object exposes
   inflection-class membership on one interface and phonological environments on
   another: "Same object, different interfaces" (C-M4-01). Resolve properties before
   guessing.
8. **Borrow feature objects, do not recreate them.** Attach the *same*
   feature-specification and value objects the already-working affix uses, not new
   look-alikes (L-M6-04).
9. **Check the environment string is not empty** before believing an allomorph is
   conditioned (L-M8-04).

---

## 6. Where the corpus disagreed with itself

Summarized here; argued in full in
[README section 4](../README.md#4-conflicts-and-divergences).

| Question | Early answer | Late answer | This table follows |
|---|---|---|---|
| Grammatically-conditioned stem alternation | stem name keyed to a tense feature (M4) | **past-variant entry with its own MSA/class** (M8), stem name retained as the selection mechanism | late (#8 + #9) |
| Affix allomorphy in general | convert everything to affix-process rules (M1) | **plain allomorph + environment / inflection class**, process rules reserved for non-concatenative cases (M3 onward) | late (#2, #12) |
| Rule environments | widen, including unanchored (M2) | **always boundary-anchored**; widen by adding another anchored RHS (M3) | late (#13) |
| Conditioning set | factor into a natural class (M3) | **also**: never extend a shared class for a local problem; sometimes use exact per-segment environments (M5, M7) | both (#3 vs #4) |
| Nominalizers | inflectional slot (M6 early) | **derivational MSA** (M6 late) | late (#16) |
| Obliques | variant entries **or** stem allomorphs (M6) | inflectional augment affix for the regular case, variant entries for the categories outside its scope (M7) -- **but the general question is unresolved** | see [open-questions.md](../open-questions.md) Q-04 |
| Which form is the lexeme form (Swahili) | most-restricted form (S1, L-S1-02) | **elsewhere form**, as F1 (S6, D-S6-04) | late (F1) |
| Verb extensions (Swahili) | inflectional slots (S1-S6) | **derivational MSAs between valency subcategories** (S7, V-S7-01) | late (#16, #35) |
| Optionality that differs by construction (Swahili) | relax the slot (S2) | **clone the slot / separate template** (S5-S7), with one unresolved relapse (TAM2, C-S7-02) | late (#29) |

---

## 7. Merge seam

When Matthew's process is merged, add a column to the table in section 1: **"Matthew's
choice"**, with its own evidence. Where the two differ, keep both rows and record the
reason rather than picking a winner -- a difference here is likely to be a real
difference in language type or in project goal, not an error.

**Status (merged, shards S1-S11, both machines):** done as section 1b plus rows 25-37.
Rows 25-31 came from S1-S5; rows 32-37 and the late entries in 1b from S6-S11. The
former largest open item, row 2 versus L-S1-02 (Q-37), was settled toward F1 by Matthew
himself (D-S6-04). The largest open items now are glide formation (row 13 / 37: rule,
allomorphs or exception feature) and lexicalized derived stems (row 31 / 35, *zalia*,
*zaliwa*). Rows marked "parse outcome not logged" rest on S6-S7 logs, which kept no
tool output.

### Cross-cutting rules added from the Swahili corpus

10. **Key every target by GUID** (or name + catalog id), never by hvo -- hvos shifted
    within one session (C-S1-05, C-S3-05, D-S4-07).
11. **Give a zero morph or an agreement affix the same features the stems carry.**
    Features with no overlap cannot clash, so nothing blocks them (L-S4-01).
12. **Clone, do not mutate, a shared slot** when one construction needs different
    optionality (L-S5-02).
13. **Swap a lexeme form and an allomorph by moving the owned objects**, as FieldWorks'
    own `SwapAllomorphWithLexeme` does (insert the old lexeme into the alternate forms,
    then assign the allomorph as the lexeme form). Object identity survives, so stored
    analyses stay valid; check morph-bundle reference counts before and after. Never
    rewrite form strings or guess a method by name: `ReplaceMoForm` left an orphan entry
    in the work project (D-S6-05, L-S6-02, C-S6-01).
14. **Write the design reasons into the project.** A template's Description records its
    anchor, its reasoning, what was deliberately not built, and known gaps ("DO NOT
    merge Subj with Subj2"). Read it before editing the template: the 09-13
    contradictions came from sessions that did not (D-S6-09, D-S7-02, C-S7-02).
15. **Model by analogy to a parsing comparator.** Before creating an entry, read a
    *parsing* entry of the same kind and copy its POS, feature names and inflection
    class verbatim (D-S10-07).
16. **Count the users of a feature value before keying anything to it.** Unification is
    by exact value: concords keyed to class 1 miss the 40 stems tagged 1a. This is rule
    1 applied to feature values (D-S8-11).
17. **An allomorph no analysis ever selects is a defect signal.** Count usage per stored
    allomorph; a conditioned lexeme form beside an unconditioned alternate is swapped
    (L-S6-01). An alternate list with no environments at all usually hides derivation
    stored as allomorphy (L-S10-04).
18. **"Parsed" is not "correct".** More than about three analyses on a short noun is an
    over-generation signal to inspect, not a success (L-S10-05, L-S11-02).

### Suppressing an entry from the parser (recorded, not recommended)

The Swahili project kept whole-word possessives, a duplicate stem and the class-16 null
prefix listed but unparsed with `DoNotUseForParsing=True` (D-S7-04, V-S7-02, D-S8-12; 33
entries by 09-20). **That flag is deprecated in this repo's tooling**: do not use it in
recipes or fix-ups, or as a model for new API. Its effect on HermitCrab was never shown
(C-S8-07), and on 09-24 stored analyses still used the flagged null prefix (V-S9-03).
Prefer retiring a redundant entry once its compositional analysis parses (row 20); a
separate "listed but not parsed" convention is an open question
([open-questions](../open-questions.md), Swahili section).
