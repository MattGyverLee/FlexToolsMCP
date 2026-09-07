# Domain Expert Review — Swahili Concord/Class Modeling
**Date:** 2026-09-06 | **Domain:** Swahili/Bantu morphology (FLEx) | **Status:** Decisions with flagged uncertainties

## B2 — Bound stems in slotless categories (det/part)

**(a) `*yake`/`*zao`:** These are transparently `ya-` (cl9 concord)+`-ake` and `za-`(cl10)+`-ao`, now fully generable by the working possessive-concord template. They are redundant, not distinct lexemes. Do not delete (risk of orphaning existing `WfiAnalysis` records in texts). Mirror the `cha-` precedent already used this session: **disable both for parsing**, add an entry note pointing to the compositional `ya+ake`/`za+ao` analysis.

**(b) `*juu`:** "up/above" is a free adverbial (`juu ya nyumba`), not a bound class-agreeing stem — it takes no concord. **Convert to a free stem**, category Adverb/Locative-adverb; drop the bound-stem coding.

**(c) `-pi` / `-ngapi`:** `-ngapi` ("how many") patterns exactly like a numeral and should simply **join category `num`, reusing the existing NumConcord slot** — no new mechanism needed. `-pi` ("which") is determiner/pro-form-like; put it in `pro-form` reusing the same concord-slot machinery just built for `-ake`. **OPEN QUESTION FOR USER:** class-1 `-pi` is irregular (`yu-pi`, not `*m-pi`/`*mw-pi`), so a `yu-` concord sense may not yet exist in the pro-form concord set — confirm before assuming this parses cleanly once slotted.

**(d) `*hivi`:** This is a fully inflected, irregular proximal demonstrative (class 8; part of the suppletive `huyu/hawa/huu/hii/hivi…` paradigm), not a compositional bound+concord form. **Convert to free stem**, category `pro-form` (demonstrative); no concord slot attached.

**DECISION:** Disable `*yake`/`*zao` for parsing (keep entries); make `*juu` a free adverb stem; move `-ngapi` into `num`/NumConcord and `-pi` into `pro-form`/concord-slot (pending the yu- check above); make `*hivi` a free demonstrative pro-form.

## B3 — `marafiki` / class 1a-2 pattern

This is the standard Bantu 1a/2 mismatch: shape borrows the class-6 `ma-` plural marker, but agreement stays class 2 (`marafiki wangu wazuri`, not class-6 agreement). The correct, generalizable fix is **not** a one-off irregular form on `rafiki` — it is a **second sense/MSA on the existing `ma-` ClassPrefix entry** (same phonological shape, homophonous prefix), carrying `BantuPl:2` instead of `BantuPl:6`. This automatically unifies with any stem independently marked `BantuPl:2` (rafiki, daktari, padri, and other 1a/2 nouns), fixing the whole subclass at once rather than per-lexeme.

**OPEN QUESTION FOR USER:** confirm whether this project's convention for other homophonous class markers (e.g., `m-`/`mw-` covering both cl.1 and cl.3) is "one entry, multiple senses" or "duplicate sister entries." Follow whichever precedent already exists for consistency rather than introducing a second pattern.

**DECISION:** Add a second MSA/sense to the existing `ma-` ClassPrefix entry with `BantuPl:2`, leaving the existing `BantuPl:6` sense untouched.

## B5 — Adjectival Concord feature table

Each prefix gets exactly one (or, for genuinely syncretic pairs, two) non-`NC NA` values; everything else is `NC NA`.

| Form | Class | BantuSG | BantuPl | BantuMany | Confidence |
|---|---|---|---|---|---|
| ch | 7 (pre-vowel allomorph of ki-) | NC 7 | NC NA | NC NA | High |
| ji | 5 | NC 5 | NC NA | NC NA | High |
| ku | 17 (locative, general/direction) | NC NA | NC NA | NC NA (see note) — set BantuSG: NC 17 | — | Medium |
| ma | 6 | NC NA | NC 6 | NC NA | High |
| mi | 4 | NC NA | NC 4 | NC NA | High |
| mu | 18 (locative, interior) | NC 18 | NC NA | NC NA | Medium-High |
| mw | 1/3 (pre-vowel) | NC 1 | NC NA | NC NA (cl.3 shares same shape/feature) | High |
| ny | 9/10 (pre-vowel, syncretic) | NC 9 | NC 10 | NC NA | Medium |
| pa | 16 (locative, specific place) | NC 16 | NC NA | NC NA | High |
| u | 11 / 14 (count vs. abstract-mass, shared shape) | NC 11 | NC NA | NC 14 | **Low — OPEN QUESTION** |
| vi | 8 | NC NA | NC 8 | NC NA | High |
| wa | 2 | NC NA | NC 2 | NC NA | High |

**OPEN QUESTION FOR USER (ku):** could plausibly be class 15 (infinitives, "kusoma kuzuri") instead of 17. I favor 17 because it pairs naturally with `pa`(16)/`mu`(18) as the locative triad, and infinitives don't take numeral concord — but confirm against real test data.
**OPEN QUESTION FOR USER (u):** class 11 vs. 14 concord is genuinely unsettled even in reference grammars (many speakers use class-3 `m-` for class-11 nouns like `ukuta`). I've used `BantuMany` for the class-14 abstract/mass sense (that's exactly what this feature exists for) and `BantuSG` for class-11 count nouns, letting one prefix serve both — verify against real "Try A Word" behavior on a class-11 test noun before trusting this row.

**DECISION:** Use the table above as authored, with `ku` and `u` flagged for empirical verification before being treated as final.

## B4 — Predicted rejection reasons

- **`matunda`:** Features nominally unify, so failure is likely **not** feature-based but a **morph-type/Inflection-Class gap**: FLEx's slot-filler restrictions (independent of the feature-unification check) may not list "bound stem" as an accepted morph type for the ClassPrefix slot, or `tunda` hasn't been assigned to the Inflection Class the `ma-`(6) affix's slot expects. Check the noun template's allowed morph types for the stem slot and `tunda`'s Inflection-Class assignment.
- **`msituni`:** Likely a **missing/wrong suffix slot**: the noun inflectional template may only define prefix slots (ClassPrefix), with no suffix position for `-ni` at all, or `-ni`'s MSA specifies it attaches to a different output category (e.g., "loc") than the plain "n" the ClassPrefix+stem combination produces. Check whether `-ni` is modeled as inflectional-in-template vs. a separate derivational step that never gets chained after the noun template.
- **`wenye`:** Most likely a **category/template mismatch**: `enye` is tagged plain noun ("n"), so the parser tries the ordinary noun ClassPrefix template (m-/wa-/ki-…), but `-enye` is actually a bound relative-concord form (parallel to `-ake`) that needs the pro-form concord-slot template, not the noun template — and the class-2 concord prefix required for `wenye` may not be a valid filler of the plain noun ClassPrefix slot's inflection class. Recommend recategorizing `enye` alongside `-ake`/`-ao` under the concord-slot mechanism rather than as an ordinary noun stem.

**DECISION:** Treat all three as template/slot-architecture bugs, not feature-unification bugs; verify each against the specific "Try A Word" rejection message before implementing fixes.

---

**Summary:** Delivered linguistic decisions for B2 (disable redundant possessive forms, free-stem `juu`/`hivi`, slot `-pi`/`-ngapi` into pro-form/num concord), B3 (add BantuPl:2 sense to `ma-` for 1a/2 nouns), B5 (full 12-row nagr feature table, `ku`/`u` flagged for verification), and B4 (predicted template/slot-architecture causes for matunda/msituni/wenye, not feature mismatches).

---
---

## Editorial notes added on persistence (not part of the domain review)

This report was returned inline because the reviewing agent's toolset had no Write/Edit/Bash;
the body above is reproduced verbatim. Two mechanical problems in it need the author's
clarification before the B5 table is implemented:

1. **The `ku` row is malformed.** It has seven cells against the table's six columns, and its
   cell text contradicts itself — `BantuMany` reads `NC NA (see note) — set BantuSG: NC 17`
   while the `BantuSG` cell reads `NC NA`. The intent appears to be
   `BantuSG: NC 17 | BantuPl: NC NA | BantuMany: NC NA`, but that must be confirmed, not
   assumed — and it is separately flagged as a class 15-vs-17 open question.
2. **`mw` and `ny` fold two classes into one row.** `mw` is given `BantuSG: NC 1` with a
   parenthetical that class 3 "shares same shape/feature", and `ny` is given both
   `BantuSG: NC 9` and `BantuPl: NC 10`. Since the project's existing ClassPrefix entries model
   cl.1 and cl.3 as *separate* entries (`m-1` SG:1, `m-2` SG:3), a single `mw` sense carrying
   only SG:1 will not unify with a class-3 stem. This may need two senses per form, matching the
   B3 recommendation's own "second sense on the existing entry" pattern.

Neither is a linguistic disagreement — both are places where the table as written cannot be
typed in verbatim, which was its stated purpose.
