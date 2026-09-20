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
| 23 | A category whose members never inflect | -- | The POS owns **zero** templates and slots | an empty template | L-M2-10 |
| 24 | A bare stem that cannot surface as a word | morphotactic | Mark the relevant slot **non-optional** | optional (it will over-generate bare stems) | **D-M1-02** |

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

---

## 7. Merge seam

When Matthew's process is merged, add a column to the table in section 1: **"Matthew's
choice"**, with its own evidence. Where the two differ, keep both rows and record the
reason rather than picking a winner -- a difference here is likely to be a real
difference in language type or in project goal, not an error.
</content>
</invoke>
