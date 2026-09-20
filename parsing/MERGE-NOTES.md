# Merge Notes

[Back to README](README.md)

Two things live here:

1. **Section 1-3: seams for merging Matthew's process** into this spec later.
2. **Section 4: the MCP parsing-tooling requirements** this spec implies -- aggregated
   from every stage's Automation Notes, so it can be read as a backlog.

---

## 1. What this spec currently is

- **One operator** (Ron), **one language** (Malayalam), **one project**, six days of
  logs (2026-09-10 to 09-15), plus one earlier deck project in another language
  (German, 09-04 to 09-05) contributing process hygiene only.
- **No native speaker of the target language was involved.** Every linguistic claim is
  a hypothesis. See [README section 1](README.md#1-where-this-came-from).
- **Parsing was invoked out of band** (FLEx GUI parser; a HermitCrab CLI capability
  solved in a session not in this corpus). Stage 11 is written for in-MCP tooling that
  does not fully exist yet.

Merging Matthew's process is therefore not "adding more evidence for the same claims" --
it is the **first independent test** of whether any of this generalizes.

---

## 2. Merge seams, by file

Each stage file ends its Provenance section with a `**Merge seam:**` line. Consolidated:

| File | What to capture from Matthew | Likely divergence |
|---|---|---|
| [README](README.md) | his corpus, dates, language, project goal; add his shard table | -- |
| [00-overview](00-overview.md) | his principles; test each of P1-P10 against his practice | P2 (inflection-first) and P6 (proof-of-recipe) are the most likely to be idiosyncratic to Ron |
| [01 Survey](stages/01-project-survey-and-inventory.md) | scope and what he records | he may not survey at all if he owns the project alone |
| [02 Phonemes](stages/02-phoneme-inventory.md) | his inventory source | may derive it from a writing-system definition or LIFT import rather than authoring it |
| [03 Features](stages/03-phonological-features.md) | whether he uses features at all | **high** -- if he uses segment-list classes only, Stage 03 becomes optional and Stage 04's decision tree needs a second branch |
| [04 Natural classes](stages/04-natural-classes.md) | his threshold and naming | reconcile **by membership, not by name** |
| [05 Categories](stages/05-categories-and-templates.md) | his category inventory and slot conventions | whether he uses shared parent-category slots at all |
| [06 Population](stages/06-stem-and-affix-population.md) | staging format, field conventions | data module vs JSON vs LIFT/CSV import |
| [07 Allomorphy](stages/07-allomorphy-modeling.md) | **his construct preferences** | **highest** -- see section 3 |
| [08 Rules](stages/08-phonological-rules.md) | rule types used; ordering policy | he may use rule types the corpus only enumerated (metathesis, iteration contexts) |
| [09 Compounds/clitics](stages/09-compounding-and-clitics.md) | clitic conventions | whether his language/project uses compound rules at all |
| [10 Paradigm texts](stages/10-paradigm-text-construction.md) | sampling strategy | he may go straight to real text, merging Stages 10 and 12 |
| [11 Parse/repair](stages/11-parse-and-repair-loop.md) | parser used; bucket definitions; acceptance thresholds | **high** -- GUI parser vs HermitCrab CLI vs new in-MCP tooling |
| [12 Real corpus](stages/12-real-corpus-stress-test.md) | corpus sources, licensing, whether he frequency-orders the queue | -- |
| [13 Cleanup](stages/13-cleanup-and-consolidation.md) | cadence and redundancy tolerance | -- |
| [reference/flex-modeling-decisions](reference/flex-modeling-decisions.md) | **add a "Matthew's choice" column** | see section 3 |
| [reference/natural-classes](reference/natural-classes.md) | section 1 is shared; section 2 splits per language | -- |
| [reference/malayalam-morphophonology](reference/malayalam-morphophonology.md) | **does not merge** -- becomes one of several `reference/<language>-*.md` | promote leaked language-neutral content out of it first |
| [reference/allomorphy-environments](reference/allomorphy-environments.md) | **does not merge**; promote the syntax table (section 1) if a second project confirms it | -- |
| [conventions/flex-data-conventions](conventions/flex-data-conventions.md) | his conventions alongside, with provenance | where two conflict and both work, **record both** and note which project uses which |
| [conventions/ai-collaboration-guardrails](conventions/ai-collaboration-guardrails.md) | merge **by rule, not by source**: confirming evidence joins the existing rule; contradicting evidence keeps both and marks the divergence | -- |
| [evidence/directive-index](evidence/directive-index.md) | append his shards' ids as new sections; keep the one-row-per-id invariant | -- |
| [open-questions](open-questions.md) | resolve every question marked *Audience: Matthew* | -- |

---

## 3. The three places where a merge will hurt

### 3.1 The modeling decision table

[`reference/flex-modeling-decisions.md`](reference/flex-modeling-decisions.md) section 1
is the spec's main claim to generality, and it is built from **one** analyst's practice
on **one** language. Rows 8-9 (grammatically-conditioned stem alternation) in
particular encode a conclusion Ron reached only on the last day of the corpus, after
reversing an earlier one.

**Merge instruction:** add a "Matthew's choice" column. Where the two differ, **keep
both rows** and record the reason. A difference here is more likely to be a real
difference in language type or project goal than an error by either party. Do not
silently pick a winner.

### 3.2 The conflicts section

[README section 4](README.md#4-conflicts-and-divergences) currently resolves every
conflict toward the late-corpus form, on the grounds that later practice is more
informed. That is a reasonable default **within one operator's arc**. It is not
automatically right across two operators: Matthew's practice may look like Ron's
*early* practice and be right for his situation.

**Merge instruction:** when Matthew's practice matches an early-Ron form this spec
overrode, re-open the conflict rather than treating him as behind.

### 3.3 The status of the linguistic content

The `reference/` files carry per-item status values (`asserted-by-Ron`,
`AI-proposed-accepted`, `unresolved`, `revised`). If Matthew's project has native-speaker
involvement, his content will carry a genuinely stronger status
(`verified-by-native-speaker`) that this corpus cannot claim.

**Merge instruction:** extend the status vocabulary rather than flattening it. Do not
let stronger-status content next door imply that this corpus's content is verified.

---

## 4. MCP parsing-tooling requirements

Aggregated from every stage's Automation Notes. FLExToolsMCP is gaining parsing tooling
based on Ron's HermitCrab CLI solution (D-M5-06); this is the requirements list that
falls out of the corpus.

Priority reflects how often the corpus hand-rolled the capability and how much damage
its absence caused.

### P0 -- the parsing loop itself ([Stage 11](stages/11-parse-and-repair-loop.md))

| # | Requirement | Why |
|---|---|---|
| T-01 | **`parse_text(text)`** in-band: per wordform, analysis count and per analysis the full morpheme breakdown (entry, allomorph, slot, MSA), plus timing | Parse results were exchanged out of band and are **not recoverable from the logs** (M5 §7) |
| T-02 | **`explain_parse_failure(surface_form)`** -- how far the parser got: which stem allomorph matched, which suffix was attempted, which environment or inflection-class restriction rejected it, which rule did or did not apply | The single highest-value missing tool. Every diagnostic operation in M1, M2, M3, M5, M8 is a hand-rolled partial version of it |
| T-03 | **`parse_diff(prev_run, cur_run)`** -- newly failing / newly passing / changed analysis count | D-M3-01's mandatory regression check, currently manual |
| T-04 | **Automatic bucket partition** (zero / one / duplicate-signature multi / distinct-signature multi), grouping multi-analyses by morpheme signature | Mechanizes D-M3-04's duplicate-vs-genuine-ambiguity distinction |
| T-05 | **Parse-run persistence** so runs can be diffed and failure lists are not lost | M5 §7 item 4 |
| T-06 | **`parse_forms([...])`** -- parse an ad hoc list without creating a text | Hypothesis testing during repair |
| T-07 | **Parse timing per run and per word, diffed against the previous run** | D-M3-02 made parse time a first-class metric; it was measured by stopwatch |

### P0 -- the atomicity gap ([Stage 06](stages/06-stem-and-affix-population.md), [Stage 13](stages/13-cleanup-and-consolidation.md))

| # | Requirement | Why |
|---|---|---|
| T-08 | **A transactional / rollback-capable write mode** | Three shards record: "the atomicity unit for this whole session is the SESSION, not the operation" (M5 §6, M6 §6, M8 §6). It directly caused half-built entries (C-M6-02). Most of the conventions in [flex-data-conventions §6](conventions/flex-data-conventions.md) are mitigations for its absence |
| T-09 | **A guarded bulk-delete primitive**: requires an explicit target list, or a predicate **plus** a category filter; refuses senseful items by default; backs up content; writes a log; replayable in reverse | C-M7-01 (92 + 6 wrongly deleted), D-M5-10, D-M7-02 |

### P1 -- blast-radius and lint tools ([Stages 04, 07, 08](stages/04-natural-classes.md))

| # | Requirement | Why |
|---|---|---|
| T-10 | **`referrers_of(class \| environment \| inflection_class \| stem_name \| feature)`**, surfaced **automatically** on any write touching a shared object | C-M5-05 -- the corpus's most expensive class-related mistake |
| T-11 | **`restriction_impact(allomorph, proposed_classes)`** -- which entries would be excluded | C-M5-06 (over-narrowing broke a sibling class) |
| T-12 | **Unanchored-context lint**: "rule R has an RHS whose context is a bare natural class with no boundary marker" | A one-line static check that would have prevented a 4-minute corpus parse time (L-M3-02) |
| T-13 | **Allomorph-representation lint**: entries mixing plain and process alternates; unreachable citation forms; allomorphs identical to their entry's lexeme form; environments whose string is empty | C-M1-05, C-M1-06, L-M3-05, L-M8-04 |
| T-14 | **Inflection/derivation lint**: warn when a template-slotted affix's MSA changes the part of speech | C-M6-03 |
| T-15 | **Writing-system lint on environment strings** | D-M3-05 ("otherwise I get boxes") |
| T-16 | **Duplicate-object detection** across classes, environments and possibility items | D-M5-05, D-M7-05 |
| T-17 | **Required-fields lint**: entries missing a WS form, gloss, sense, or POS | D-M2-03 |

### P1 -- coverage and redundancy reports

| # | Requirement | Why |
|---|---|---|
| T-18 | **`environment_coverage_report(texts)`** -- for each allomorph and environment, does any test wordform exercise it? A **test-coverage report for a grammar** | D-M2-06's sampling criterion, never measured (Q-22) |
| T-19 | **`allomorph_usage_report()`** -- usage count per stored allomorph across all analyses | M1 op 41, hand-rolled |
| T-20 | **`redundancy_report()`** -- rule-derivable allomorphs, lexeme-form clones, zero-usage allomorphs, duplicate possibility items, orphaned contexts, zero-referrer classes | M1 op 35, L-M3-05, Stage 13 |
| T-21 | **`convention_audit(phenomenon)`** -- how many entries use representation A, how many B, how many both | L-M6-01, counted once and never resolved (Q-04) |
| T-22 | **Over-generation probing**: generate what the grammar permits for a paradigm and diff against attested cells | D-M8-05 was found by reasoning; bucket D is otherwise invisible (Q-25) |
| T-23 | **`failures_to_candidates(parse_run)`** -- deduplicated, normalized candidate list with a category guess | D-M8-04, built by hand each round |
| T-24 | **Coverage statistics per run** (token, type, frequency-ordered failures) | Stage 12 work queue ordering |

### P2 -- construction and survey helpers

| # | Requirement | Why |
|---|---|---|
| T-25 | **`survey_project()`** -- whole pre-state in one call; plus **`diff_snapshot()`** | Every shard opens by re-writing the same survey code; C-M2-06 would have been resolved in seconds |
| T-26 | **`verify_inventory_covers(text_or_wordlist)`** -- decompose and report undefined graphemes | Stage 02, done by hand every time |
| T-27 | **`assign_feature_matrix(table)`** with the distinctiveness + minimality proof as a **refusal gate**; plus `diff_feature_matrix(table)` | D-M1-04, D-M1-06 |
| T-28 | **`propose_natural_classes()`** -- cluster identical conditioning sets, report sharing counts and feature-definability; **`check_class_distinguishability(members)`** | D-M3-05's threshold test; L-M7-03's failure |
| T-29 | **`clone_template(from_pos, to_pos)`** | D-M8-03's build-by-analogy |
| T-30 | **Affix-process rule construction as one call**, with factory-seeded-node cleanup and well-formedness validation | M7 ops 19-20 |
| T-31 | **Variant-vs-allomorph conversion primitive**, both directions | Done, reverted, then bulk-applied 101 times across the corpus |
| T-32 | **`rule_derives(rule, input)`** -- apply one rule in isolation without a full parse | The corpus had no way to test a rule except by parsing |
| T-33 | **`explain_allomorph_selection(entry, surface_form)`** | The write-side counterpart of T-02 |
| T-34 | **`why_didnt_this_compound(form)`** | M6 op 30, asked by hand and left unanswered (Q-10) |
| T-35 | **`reconcile_import(plan)`** -- present / missing / present-but-incomplete | D-M5-13 |
| T-36 | **Recursive possibility-list resolution** as a first-class helper | C-M6-02 |
| T-37 | **Polymorphic-safe allomorph read/write wrappers** (stem vs affix subtype) | C-M1-02, C-M2-01 |
| T-38 | **Automatic citation-form population** for affix entries | M7 §6 ("-???" display) |
| T-39 | **Enclitic "attaches to" helper** | M2 §6 -- no wrapper exists, raw LCM required |
| T-40 | **Category-name registry** so creation and consumption cannot diverge | C-M5-01 (69/69 rows failed) |
| T-41 | **Surface the FLEx "apply rules to clitics" setting** through the MCP | D-M3-03 -- a data-level diagnosis chasing an application-level cause |

### P2 -- observability

| # | Requirement | Why |
|---|---|---|
| T-42 | **Overflow-safe output**: spill large report payloads to a file automatically | M8 §6 (320 messages truncated to 100) |
| T-43 | **Persist report output in the operation log**, not only source code and message counts | This is why Q-08, Q-13, Q-17, Q-20 are open at all. The log format is the reason several conclusions in this corpus are unrecoverable |

---

## 5. Suggested merge order

1. Ingest Matthew's shards and extend
   [`evidence/directive-index.md`](evidence/directive-index.md) first -- the index is
   the audit surface for everything else.
2. Run his section-5 workflow stages against this stage list. **Do not renumber**
   stages unless his evidence shows a genuinely different decomposition; prefer adding
   sub-steps and alternate paths inside existing stages.
3. Add the "Matthew's choice" column to the modeling decision table.
4. Re-open [README section 4](README.md#4-conflicts-and-divergences) for any conflict
   his practice touches.
5. Split `reference/` per language; promote anything language-neutral that has leaked
   into the Malayalam files.
6. Merge the guardrails by rule.
7. Close every open question marked *Audience: Matthew*.
8. Re-derive the tooling backlog in section 4 -- his process will add requirements and
   may demote some of these.
</content>
</invoke>
