# Natural Classes -- Inventory, and When to Make One

[Back to README](../README.md) | Used by [Stage 04](../stages/04-natural-classes.md)

Two halves: a **language-neutral decision procedure** (section 1), and the **classes
this project actually built** (section 2), which are Malayalam hypotheses and are
unverified by a native speaker -- see the framing in
[`malayalam-morphophonology.md`](malayalam-morphophonology.md).

---

## 1. When to make a natural class vs. use a literal environment

### 1.1 The governing directive

> "would it work to make a natural class of each set of 4 that would be easier to
> maintain. If it works, give it an English name, remember this, if there is just one
> environment (thus not helpful to make a natural class) and it uses a vernacular
> letter, the whole environment should be in the vernacular WS, otherwise I get boxes."
> (D-M3-05, restated as the operative rule across ~8 subsequent operations)

Two independent rules in one sentence:

1. **Threshold.** Four or more allomorphs sharing a conditioning set earns a named
   class. Fewer does not.
2. **Writing system.** A one-off environment containing a vernacular character must be
   authored **entirely** in the vernacular writing system. Mixing writing systems
   inside one environment string renders as boxes in the FLEx UI. This is a real
   data-quality rule with a visible failure mode.

### 1.2 The decision procedure

```
Is the conditioning set shared by 4+ allomorphs or rules?
  NO  -> literal environment.
         Contains a vernacular character? -> author the WHOLE string in the vernacular WS.
  YES -> continue
         |
Is the set cleanly definable as a feature conjunction,
and does that conjunction pick out exactly the intended members?
  NO  -> either a SEGMENT-LIST class (if the members are stable and the set is
         genuinely reused), or exact per-segment environments (if the members
         are few and not a coherent set).
  YES -> FEATURE-BASED class.
         |
Is the conditioning phonological at all?
  NO  -> this is not a natural class. Use an INFLECTION CLASS (lexical/grammatical
         subclass) or a STEM NAME (feature-conditioned). See flex-modeling-decisions.md.
  YES -> create the class. Give it a descriptive ENGLISH name and an abbreviation.
```

### 1.3 The two counter-pressures

Both were learned by being wrong.

**(a) Do not extend a shared class to fix a local problem.**

> "Revert the shared PsF change and add a dedicated nnu past class with its own
> allomorph and environment." (D-M5-14)

Adding one phoneme to a project-wide class to make one verb subclass work changed
behavior everywhere (C-M5-05). The correct move when the fix is **local to a lexical
subclass** is a dedicated inflection class plus a **literal, non-shared environment**.
Check referrers before touching any existing class.

**(b) A class is only usable if its members are actually distinguishable.**

A purpose-built "Enclitic onset" class was created, then abandoned in favor of four
exact per-segment environments, because a feature-bundle comparison showed the four
matras were not separable by feature structure alone (L-M7-03). **Test
distinguishability before relying on a class.**

### 1.4 Naming

The corpus's names are descriptive English phrases naming the class's **function**,
not its phonology: "Case suffix onset", "Post-augment case onset", "Plural final
chillu", "Nya-past stem final", "Past stem final", "Enclitic onset". Abbreviations are
short mixed-case tags (CsOn, PACs, PlF, NyF, PsF, EncOn).

This is legitimate and deliberate -- the point of the class is maintainability
(D-M3-05), and a functional name tells the maintainer why it exists. But it means
**some of these are stipulative sets, not phonological natural classes**, and the
naming should not disguise that.

### 1.5 Hygiene

- **Reuse, do not duplicate.** Look up an existing class or environment object with the
  same semantics rather than creating a second one (D-M7-05). The human and a script
  can independently create same-named items; reconcile rather than leaving both
  (D-M5-05).
- **Recompute and print membership** after creating a feature-based class, and verify
  it against intent (M2 op 8).
- **Track referrer counts** so dead classes can be retired in
  [Stage 13](../stages/13-cleanup-and-consolidation.md), and so a still-referenced
  class is never deleted.
- **Re-verify membership after any inventory change.**

---

## 2. The classes this project built

**Unverified Malayalam hypotheses.** Members are given as the shards give them.

### 2.1 Broad, feature-based classes

| Name | Abbr | Definition | Members | Status | Evidence |
|---|---|---|---|---|---|
| Consonant | -- | `cons = +` | 44 | `asserted-by-Ron` | L-M1-06 |
| Vowel | V | `cons = -`, `son = +` | 23 | `AI-proposed-accepted` | L-M1-02, L-M1-06 |
| Syllabic | Syl | `syl = +` | 49 | `AI-proposed-accepted` | L-M1-04 |
| Vowel sign | Vs | `cons = -`, `son = +`, `syl = -` | -- | `AI-proposed-accepted` | L-M1-04, L-M5-05 |
| Virama | Vir | `cons = -`, `son = -` | -- | `AI-proposed-accepted` | L-M2-06 |
| Anusvara | Anu | `cons = +`, `syl = -`, `lab = +` | -- | `AI-proposed-accepted` | L-M2-06 |
| Chillu (coronal) | -- | `cons = +`, `syl = -`, `cor = +` | 5 | `AI-proposed-accepted` | L-M1-01 |
| Chillu (velar) | -- | `cons = +`, `syl = -`, `cor = -`, `lab = -`, `cont = -` | 1 | `AI-proposed-accepted` | L-M1-01 |
| Chillu l | -- | `cons = +`, `syl = -`, `cor = +`, `ant = +`, `lat = +` | -- | `AI-proposed-accepted` | L-M3-01 |
| Chillu n | -- | (referenced as a trigger class; definition not captured) | -- | `AI-proposed-accepted` | L-M2-01 |

The feature-based classes replaced an earlier segment-based Consonant/Vowel pair,
which was retired (M1 op 28).

### 2.2 Function-named, segment-list classes

These are the maintainability classes D-M3-05 called for. Each was created because a
literal set was being repeated across allomorphs.

| Name | Abbr | Members (as recorded) | Purpose | Status | Evidence |
|---|---|---|---|---|---|
| Case suffix onset | CsOn | aa, i, e, ee | vowel-initial case suffixes attaching directly to certain stem-final allomorphs | `AI-proposed-accepted` | L-M3-08 |
| Post-augment case onset | PACs | aa, e, ee, virama | case attachment after the -in- oblique augment | `AI-proposed-accepted` | L-M3-07 |
| Plural final chillu | PlF | chillu rr, chillu LL | constrains the genitive elsewhere form so it stops overgenerating | `AI-proposed-accepted` | L-M3-14 |
| Nya-past stem final | NyF | i, rr | restricts the nya-initial past series; "never after a derived stem" | `AI-proposed-accepted` | L-M3-09 |
| Past stem final | PsF | (shared, project-wide; membership not fully captured) | past-suffix conditioning | `AI-proposed-accepted` | L-M5-09 |
| Past stem T | PsT | (geminate-final past stems) | past-stem conditioning | `AI-proposed-accepted` | L-M4-03 |
| Conditional final | CondF | nga, ta, tta, ka; later extended with na, rra, la; explicitly excluding ya | replaced a class-based restriction that was blocking derived stems | `asserted-by-Ron` | L-M4-01 |
| NpF | NpF | (created alongside PsT for the new conjugation classes) | -- | `AI-proposed-accepted` | M4 op 3 |
| Enclitic onset | EncOn | four matra vowels | intended to scope the anusvara rule | **`revised` -- created then abandoned** for four exact per-segment environments | L-M7-03 |

### 2.3 Notes on specific classes

**PsF is the cautionary tale.** It is shared project-wide. Adding one phoneme to it to
make -nna past stems take the right suffix had far broader scope than intended
(C-M5-05). The fix was to revert and create a dedicated inflection class ("Past -nnu")
with its own literal environment (D-M5-14). **Any edit to PsF should require an
explicit referrer review.**

**EncOn is the distinguishability tale.** Created 10:24, membership inspected 10:32,
feature bundles compared 10:33, abandoned 10:35 (M7 ops 31-35). Whether the class
object was actually deleted or merely orphaned is not confirmed (M7 §7).

**CondF is the "class restriction was the wrong device" tale.** A class-based
restriction on the conditional/concessive suffixes blocked derived stems that inherit
their root's inflection class; the fix was to replace the restriction with a positive
**phonological environment** scoped to exactly the stems that should be excluded
(D-M4-01, L-M4-01). The opposite of the usual direction.

---

## 3. Merge seam

When Matthew's classes are merged:

- **Reconcile by membership, not by name.** Two projects will name the same set
  differently and different sets identically.
- Capture his **threshold** (is four the right number, or was it incidental to the
  case Ron happened to be looking at -- see
  [open-questions.md](../open-questions.md) Q-07?).
- Capture whether he uses feature-based classes at all, or only segment lists. If only
  segment lists, [Stage 03](../stages/03-phonological-features.md) becomes optional and
  section 1.2's decision tree needs a second branch.
- Section 2 splits per language; section 1 stays shared.
</content>
</invoke>
