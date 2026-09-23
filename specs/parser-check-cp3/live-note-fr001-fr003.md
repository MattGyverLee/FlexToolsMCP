# Live note: FR-001 and FR-003 (T008, T009)

**Date**: 2026-09-22 · **Project**: `IndonesianHC-Complete` · **Mode**: read-only
(`writeEnabled=False`, only `Get*`/`Is*` calls)

These two questions are open items 11 and 12 in the parent spec's register
(`specs/parser-check/SPEC.md` section 17). Neither blocks the checkpoint
(plan.md, R-08); between them they gate FR-002's refusal wording and one
sentence in the oracle.

---

## FR-003 / register item 12 -- ANSWERED: yes

**Question**: can an analysis be recorded against a text segment without any
human act?

**Answer: yes, and it is the overwhelmingly common case on a parsed project.**

Traversal of every wordform and every analysis in `IndonesianHC-Complete`:

| | |
|---|---|
| Analyses examined | 77 (complete -- not truncated) |
| Carrying **no** human evaluation | **76** |
| Of those, carrying an agent evaluation | **76** (`ICmAgentEvaluation`) |
| Carrying neither evaluation | 0 |
| Carrying a human evaluation | 1 |

Every one of the 76 reports `GetHumanEvaluation(...) is None` while
`GetAgentEvaluation(...)` returns an `ICmAgentEvaluation`, with
`GetApprovalStatus(...) == 1`. An analysis therefore reaches the record with no
human act at all, by parser action alone.

**What this settles for CP3.** The affirmed/indeterminate split (FR-042) is
sound and the indeterminate population is real rather than theoretical -- here
it is 76 of 77 analyses, 99%. It also confirms why FR-040's wording discipline
matters at this scale: a report that characterised the indeterminate population
as "unreviewed" would be characterising essentially the entire project.

This discharges the T010 gate on the description of what the indeterminate
population *contains*.

**What it does not settle.** The register's phrasing asks specifically about a
*segment assignment* arriving without a human act -- an analysis reaching
`AnalysesRS` by being offered and not overruled. The 76 above are analyses on
wordforms; none of them was observed to be segment-referenced (see the caveat
below). So the weaker-than-tacit population the register worries about is
neither demonstrated nor excluded here. CP3 does not lean on that distinction:
the reporting rule already declines to characterise individual analyses.

### Caveat on the segment-reference count

The probe also counted parser-only analyses that are referenced by a segment,
and got **0**. That number is **not** being recorded as a finding. It was read
through `ReferringObjects` on the raw object, which may simply not be populated
or reachable that way through the wrapper -- a zero that means "not observed"
is indistinguishable here from a zero that means "none exist". FR-050's
deletion projection depends on exactly this read, so it needs a join written
deliberately (T091) rather than an incidental attribute probe, and its
correctness is asserted by T086's fixture rather than by this number.

---

## FR-001 / register item 11 -- NOT ANSWERED

**Question**: is a text never opened for interlinear work distinguishable,
through the data model alone, from a text that genuinely contains no words?

**Status: could not be settled on the designated project. The discriminating
pair does not exist in it.**

`IndonesianHC-Complete` holds exactly two texts, and both are fully tokenized:

| Text | Paragraphs | Segments | Analysis slots on segments |
|---|---|---|---|
| Verbalizer Ortho | 1 | 1 | 38 |
| Verbalizer IPA | 1 | 1 | 38 |

Neither a never-tokenized text nor a genuinely word-empty text is present, so
there is nothing here to distinguish. Answering the question requires a project
containing at least one text that has never been opened for interlinear work.
One cannot be manufactured within CP3: creating or opening a text is a project
write, and this checkpoint ships no write path (FR-063).

**Why this does not block the checkpoint.** FR-002 was written to survive
exactly this outcome. It does not ask for a proven discriminator; it asks for a
*conservative* refusal -- a structural count that is non-zero while the unique
word count is empty, worded so that it does not assert the text has no words,
and deliberately not reusing `parse_scope_empty`. That wording is correct
whether or not the two states turn out to be formally distinguishable, because
it declines to make the claim that would depend on the answer.

**What T026 should therefore ship**: the conservative wording, with no sentence
claiming the text has never been tokenized and none claiming it is empty. The
response says what was observed -- structure present, no unique wordforms
resolved -- and stops there.

**To close this later**, probe a project carrying a text that has never been
opened in interlinear, and compare `IStText.UniqueWordforms()` and the segment
count against a text whose content is genuinely empty. Until then the register
entry stays open with this note attached.

---

## Incidental live finding -- `vernacular_ws` is load-bearing, not decorative

Recorded here because it was observed on the same run and it changes how T021,
T025 and T027 must be written.

Probing `IStText.UniqueWordforms()` on both texts of `IndonesianHC-Complete`
(confirmed present, returning `HashSet[IWfiWordform]`, 38 wordforms each):

| Text | `UniqueWordforms().Count` | `GetForm(wf)` at the default WS |
|---|---|---|
| Verbalizer IPA | 38 | real forms -- `membuɑt`, `mendɑlɑm`, ... |
| Verbalizer Ortho | 38 | **`""` -- every one empty** |

`WordformOperations.GetForm(wordform_or_hvo, wsHandle=None)` defaults to *a*
vernacular writing system. The Ortho text's wordforms are not stored in that
one, so every form reads back as the empty string while the wordform objects
themselves are perfectly present and countable.

**Why this matters to US1.** A scope resolution that reads forms at the default
writing system would report this text as 38 words of empty string -- and after
NFC de-duplication (FR-009), as a *single* empty word. That is not a crash and
not a refusal; it is a silently wrong word list, and it would be indisturguishable
downstream from a text that genuinely resolved to one word.

**Consequences, to be honoured in Phase 3:**

- T021 must resolve wordform surface forms at an **explicit** writing system,
  never the implicit default, and must skip-and-record rather than emit empty
  strings into the word list.
- T027's `vernacular_ws` fingerprint field is doing real work: two runs over
  the same texts at different writing systems genuinely are not comparable,
  and this project demonstrates the case rather than merely motivating it.
- T119's multistring / `ITsString` pattern audit has a concrete live example
  to anchor on, and this is the same class as the standing #36/#39/#40 issues
  and as the recent `grammar-health` fix that resolves multistrings at a named
  writing system (commit `b896633`).

This was not predicted by the plan. It is the second thing the live run caught
that no double would have.
