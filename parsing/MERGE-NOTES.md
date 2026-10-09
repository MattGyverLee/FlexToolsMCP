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

### Merge status (2026-10-09): both machines merged

Matthew's Swahili work (project Claude-Swahili) is merged from **both machines'**
FlexToolsMCP logs:

- **S1-S5** (86 ids, 2026-05-21 .. 09-20): one machine, no tool output.
- **S6-S11** (229 ids, 2026-09-12 .. 09-30): the second machine. Tool output is kept
  from 09-23 on, and those shards add `T-` (tooling) and `V-` (verification of S1-S5)
  rows.

Where the evidence landed:

- [evidence/directive-index.md](evidence/directive-index.md) -- the S1-S5 sections, one
  row per id.
- Each stage file -- a **"Second-Operator Evidence (Swahili)"** section placed before
  Provenance. It is kept separate from Ron's text so it can be revised.
- [reference/flex-modeling-decisions.md](reference/flex-modeling-decisions.md) -- the
  "Matthew's choice" table (section 1b), rows 25-31 (S1-S5) and rows 32-37 (S6-S11).
- [reference/swahili-morphophonology.md](reference/swahili-morphophonology.md) -- new.
- [README 4.9-4.20](README.md#4-conflicts-and-divergences) -- 4.9-4.15 from S1-S5
  (4.11 now closed, 4.12-4.14 updated by S6-S11); 4.16-4.20 new from S6-S11.
- [00-overview section 5](00-overview.md) -- P1-P10 tested against Matthew's practice,
  plus candidate principles.
- [Guardrails](conventions/ai-collaboration-guardrails.md) (section K and the S6-S11
  additions), [data conventions section 13](conventions/flex-data-conventions.md), and
  [open-questions](open-questions.md) Q-37 to Q-42 (S1-S5) and Q-43 to Q-49 (S6-S11).
- [Section 4 below](#4-mcp-parsing-tooling-requirements) -- the T-requirements now
  carry status evidence from real use of the in-MCP parse tools (S9-S11).

**What S6-S11 changed most:**

1. **"Unparsed" was mostly stale.** Queues built from stored analyses ranked words that
   already parse ([README 4.16](README.md#416-what-unparsed-means-a-stored-count-s2-s3-vs-a-live-parse)).
   Refile or `try_word` before triage.
2. **Q-37 / README 4.11 closed toward F1** by Matthew (D-S6-04).
3. **Q-40 answered for the model** (extensions derivational, S7) but with relapses
   (README 4.17).
4. **The parse loop moved in-band.** S7 drove HermitCrab by hand inside `run_module`;
   S9-S11 used `try_word`, `parse_text` with filing, `parse_diff` and `parse_sandbox`.
   Stage 11's "written as it should work" is now partly observed practice.
5. **AI-behaviour failures under broad mandates and parallel agents** (README 4.20,
   guardrails).

**Remaining gaps:**

- S6 and S7 (09-12, 09-13) have no tool output. Their results are still inferred. A
  conversation transcript for 09-12 .. 09-13 may exist in the operator's Claude Code
  project history; it was not read.
- The 09-14 log starts at op #49; ops #1-48 are not in either machine's logs.
- No native-speaker verification is recorded anywhere in the Swahili corpus.

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

Aggregated from every stage's Automation Notes. When this list was written,
FLExToolsMCP was gaining parsing tooling based on Ron's HermitCrab CLI solution
(D-M5-06). That tooling has since shipped (`flextools_try_word`, `parse_text` with
filing, `parse_status`, `parse_log`, `parse_diff`, `parse_sandbox`, `parse_release`,
`grammar_health`), and Matthew used it on a real corpus from 2026-09-23 (S8-S11).
Rows marked **S6-S11:** carry status evidence from those logs (FlexToolsMCP 2.12.0).
Later releases may have closed some gaps reported here; reconcile against the current
tool list before building.

Priority reflects how often the corpus hand-rolled the capability and how much damage
its absence caused.

### P0 -- the parsing loop itself ([Stage 11](stages/11-parse-and-repair-loop.md))

| # | Requirement | Why |
|---|---|---|
| T-01 | **`parse_text(text)`** in-band: per wordform, analysis count and per analysis the full morpheme breakdown (entry, allomorph, slot, MSA), plus timing | Parse results were exchanged out of band and are **not recoverable from the logs** (M5 §7) -- **S6-S11:** partly met. `parse_text` parses word lists and corpus scopes in-band and files results, but returns counts only; neither it nor `try_word` gives a per-analysis breakdown, so agents read stored (possibly stale) bundles instead (T-S10-03, T-S11-03, D-S11-04) |
| T-02 | **`explain_parse_failure(surface_form)`** -- how far the parser got: which stem allomorph matched, which suffix was attempted, which environment or inflection-class restriction rejected it, which rule did or did not apply | The single highest-value missing tool. Every diagnostic operation in M1, M2, M3, M5, M8 is a hand-rolled partial version of it -- **S6-S11:** partly met by the `try_word` ladder (`restricted` tests a stated decomposition; `explain` writes a trace) plus `parse_log` section=trace, a rejection histogram with the first failing rule (T-S9-01, T-S11-01). The reason stays in the trace, not the response; `restricted` needs exact headwords (T-70) |
| T-03 | **`parse_diff(prev_run, cur_run)`** -- newly failing / newly passing / changed analysis count | D-M3-01's mandatory regression check, currently manual -- **S6-S11:** met by `flextools_parse_diff` ("fixed 3, broken 0", T-S9-03); not used in a grammar-wide stage that planned manual re-parses instead (T-S10-07) |
| T-04 | **Automatic bucket partition** (zero / one / duplicate-signature multi / distinct-signature multi), grouping multi-analyses by morpheme signature | Mechanizes D-M3-04's duplicate-vs-genuine-ambiguity distinction -- **S6-S11:** still missing. Filed analyses over-generate unnoticed (Misri 10, mwana 13; L-S10-05) |
| T-05 | **Parse-run persistence** so runs can be diffed and failure lists are not lost | M5 §7 item 4 -- **S6-S11:** met with defects. Runs persist by id from 09-24, but `parse_log` could not find `try_word` runs `parse_status` had just reported (T-S10-04), and traces were pruned (T-S9-01) |
| T-06 | **`parse_forms([...])`** -- parse an ad hoc list without creating a text | Hypothesis testing during repair -- **S6-S11:** met by `try_word` and word-list `parse_text` (T-S8-01, T-S11-01); most single words return an async handle to poll (T-S10-02). Hand-driven HermitCrab inside `run_module` came first (T-S7-01) |
| T-07 | **Parse timing per run and per word, diffed against the previous run** | D-M3-02 made parse time a first-class metric; it was measured by stopwatch -- **S6-S11:** partly met. Per-word time is visible through polling (5-40 s); no per-run timing diff (T-S10-02, D-S10-05) |

### P0 -- the atomicity gap ([Stage 06](stages/06-stem-and-affix-population.md), [Stage 13](stages/13-cleanup-and-consolidation.md))

| # | Requirement | Why |
|---|---|---|
| T-08 | **A transactional / rollback-capable write mode** | Three shards record: "the atomicity unit for this whole session is the SESSION, not the operation" (M5 §6, M6 §6, M8 §6). It directly caused half-built entries (C-M6-02). Most of the conventions in [flex-data-conventions §6](conventions/flex-data-conventions.md) are mitigations for its absence -- **S6-S11:** still open. `undoable=False` left an orphan after a failed delete (T-S6-04); a rule disable never persisted while lexical writes in the same window did (C-S9-02, T-S9-06); writes before a crash were committed (C-S11-05). Filing alone has preview, confirm and backup (T-S10-06). See T-71 |
| T-09 | **A guarded bulk-delete primitive**: requires an explicit target list, or a predicate **plus** a category filter; refuses senseful items by default; backs up content; writes a log; replayable in reverse | C-M7-01 (92 + 6 wrongly deleted), D-M5-10, D-M7-02 |

### P1 -- blast-radius and lint tools ([Stages 04, 07, 08](stages/04-natural-classes.md))

| # | Requirement | Why |
|---|---|---|
| T-10 | **`referrers_of(class \| environment \| inflection_class \| stem_name \| feature)`**, surfaced **automatically** on any write touching a shared object | C-M5-05 -- the corpus's most expensive class-related mistake |
| T-11 | **`restriction_impact(allomorph, proposed_classes)`** -- which entries would be excluded | C-M5-06 (over-narrowing broke a sibling class) |
| T-12 | **Unanchored-context lint**: "rule R has an RHS whose context is a bare natural class with no boundary marker" | A one-line static check that would have prevented a 4-minute corpus parse time (L-M3-02) -- **S6-S11:** `grammar_health` now scans for path-multiplying properties (representation-variant product 1.8e10, T-S10-02); whether it includes this lint was not exercised |
| T-13 | **Allomorph-representation lint**: entries mixing plain and process alternates; unreachable citation forms; allomorphs identical to their entry's lexeme form; environments whose string is empty | C-M1-05, C-M1-06, L-M3-05, L-M8-04 -- **S6-S11:** add two checks -- a lexeme form that is conditioned while an alternate is unconditioned ("swapped", T-S6-06, L-S6-01), and environment-less allomorph lists holding derived stems (L-S10-04) |
| T-14 | **Inflection/derivation lint**: warn when a template-slotted affix's MSA changes the part of speech | C-M6-03 |
| T-15 | **Writing-system lint on environment strings** | D-M3-05 ("otherwise I get boxes") |
| T-16 | **Duplicate-object detection** across classes, environments and possibility items | D-M5-05, D-M7-05 |
| T-17 | **Required-fields lint**: entries missing a WS form, gloss, sense, or POS | D-M2-03 |

### P1 -- coverage and redundancy reports

| # | Requirement | Why |
|---|---|---|
| T-18 | **`environment_coverage_report(texts)`** -- for each allomorph and environment, does any test wordform exercise it? A **test-coverage report for a grammar** | D-M2-06's sampling criterion, never measured (Q-22) |
| T-19 | **`allomorph_usage_report()`** -- usage count per stored allomorph across all analyses | M1 op 41, hand-rolled -- **S6-S11:** still missing; hand-rolled six times in one session (T-S6-06) |
| T-20 | **`redundancy_report()`** -- rule-derivable allomorphs, lexeme-form clones, zero-usage allomorphs, duplicate possibility items, orphaned contexts, zero-referrer classes | M1 op 35, L-M3-05, Stage 13 |
| T-21 | **`convention_audit(phenomenon)`** -- how many entries use representation A, how many B, how many both | L-M6-01, counted once and never resolved (Q-04) |
| T-22 | **Over-generation probing**: generate what the grammar permits for a paradigm and diff against attested cells | D-M8-05 was found by reasoning; bucket D is otherwise invisible (Q-25) -- **S6-S11:** still missing. Manual substitute: a "No Parse" text of forms that must fail (D-S7-08). Generate through the grammar, not by string concatenation (C-S7-05) |
| T-23 | **`failures_to_candidates(parse_run)`** -- deduplicated, normalized candidate list with a category guess | D-M8-04, built by hand each round -- **S6-S11:** still missing; the frequency queue was hand-rolled four times in one day and only one was right (T-S11-06) |
| T-24 | **Coverage statistics per run** (token, type, frequency-ordered failures) | Stage 12 work queue ordering -- **S6-S11:** still missing, and needs one definition of "unparsed": three gave 14,096 / 9,066 / 0 on one day (T-S10-09, T-S9-11) |

### P2 -- construction and survey helpers

| # | Requirement | Why |
|---|---|---|
| T-25 | **`survey_project()`** -- whole pre-state in one call; plus **`diff_snapshot()`** | Every shard opens by re-writing the same survey code; C-M2-06 would have been resolved in seconds |
| T-26 | **`verify_inventory_covers(text_or_wordlist)`** -- decompose and report undefined graphemes | Stage 02, done by hand every time -- **S6-S11:** cheap variant: parse rate per grapheme (gh 7%, th 17% vs 66% overall; D-S10-06) |
| T-27 | **`assign_feature_matrix(table)`** with the distinctiveness + minimality proof as a **refusal gate**; plus `diff_feature_matrix(table)` | D-M1-04, D-M1-06 |
| T-28 | **`propose_natural_classes()`** -- cluster identical conditioning sets, report sharing counts and feature-definability; **`check_class_distinguishability(members)`** | D-M3-05's threshold test; L-M7-03's failure |
| T-29 | **`clone_template(from_pos, to_pos)`** | D-M8-03's build-by-analogy |
| T-30 | **Affix-process rule construction as one call**, with factory-seeded-node cleanup and well-formedness validation | M7 ops 19-20 -- **S6-S11:** still open; see T-72 for rule enable/disable and exception features |
| T-31 | **Variant-vs-allomorph conversion primitive**, both directions | Done, reverted, then bulk-applied 101 times across the corpus |
| T-32 | **`rule_derives(rule, input)`** -- apply one rule in isolation without a full parse | The corpus had no way to test a rule except by parsing -- **S6-S11:** met in spirit by `parse_sandbox` (T-S9-08); it crashed on a missing packaged script on 09-25 (T-S10-05) |
| T-33 | **`explain_allomorph_selection(entry, surface_form)`** | The write-side counterpart of T-02 |
| T-34 | **`why_didnt_this_compound(form)`** | M6 op 30, asked by hand and left unanswered (Q-10) |
| T-35 | **`reconcile_import(plan)`** -- present / missing / present-but-incomplete | D-M5-13 |
| T-36 | **Recursive possibility-list resolution** as a first-class helper | C-M6-02 |
| T-37 | **Polymorphic-safe allomorph read/write wrappers** (stem vs affix subtype) | C-M1-02, C-M2-01 -- **S6-S11:** still open (T-S6-05, T-S9-10) |
| T-38 | **Automatic citation-form population** for affix entries | M7 §6 ("-???" display) |
| T-39 | **Enclitic "attaches to" helper** | M2 §6 -- no wrapper exists, raw LCM required |
| T-40 | **Category-name registry** so creation and consumption cannot diverge | C-M5-01 (69/69 rows failed) |
| T-41 | **Surface the FLEx "apply rules to clitics" setting** through the MCP | D-M3-03 -- a data-level diagnosis chasing an application-level cause |

### P2 -- observability

| # | Requirement | Why |
|---|---|---|
| T-42 | **Overflow-safe output**: spill large report payloads to a file automatically | M8 §6 (320 messages truncated to 100) -- **S6-S11:** still open as a default (14,284 rows capped to 100, T-S8-05; T-S7-02) |
| T-43 | **Persist report output in the operation log**, not only source code and message counts | This is why Q-08, Q-13, Q-17, Q-20 are open at all. The log format is the reason several conclusions in this corpus are unrecoverable -- **S6-S11:** partly met from 09-23 -- output is logged but truncated at about 1-2 KB (T-S9-09, T-S10-06, T-S11-07). S6-S7 logs kept counts only (T-S6-01, T-S7-02) |

### Added by the Swahili partial merge (S1-S5)

**Confirmed by S1-S5:**

- **T-43** (report output not persisted): confirmed in every Swahili shard. It is the
  reason most Swahili results are inferred.
- **T-08** (atomicity): C-S1-01, C-S4-02, C-S5-03.
- **T-09** (guarded bulk delete): C-S1-02, C-S5-01.
- **T-01** (in-band parse): the GUI parser was run at the keyboard.
- **T-22** (over-generation probing): L-S4-01 is a mechanizable case.
- Also confirmed: T-10, T-16, T-17, T-19, T-20, T-23, T-24, T-25, T-27, T-30, T-37.

The in-band parsing tools have since shipped. Their status, from S6-S11, is given
inline on each row (**S6-S11:**) and in the S6-S11 subsection below.

#### P0 -- the analysis layer ([Stage 11](stages/11-parse-and-repair-loop.md))

| # | Requirement | Why |
|---|---|---|
| T-44 | **Approve / reject analysis with agent and reason**, recorded and queryable | Approve/reject wrappers failed silently. Raw `ICmAgent.SetEvaluation` was needed, and a heuristic was recorded as Human (C-S2-01, D-S4-02) -- **S6-S11:** partly met. Filing through `parse_text` records parser evaluations only, never Human (T-S9-04). Approve/reject with reason is still missing; a count by display name misread parser approvals as human (C-S9-03) |
| T-45 | **`analyses_violating_grammar()`** -- stored analyses whose slot sequence the current templates forbid | D-S5-03; stale analyses also caused a misdiagnosis (C-S2-05) |
| T-46 | **`slot_usage_report()`** -- per-slot usage across all analyses (the slot twin of T-19) | D-S4-04's "ZERO analyses project-wide" test |
| T-47 | **Interlinear helpers**: pick an analysis by morph signature, link senses, set the word gloss, approve, point a token at an analysis, hand-build an analysis; mixed-WS paragraph creation and a per-run WS read | D-S5-06, D-S5-08, C-S5-03 |

#### P1 -- lints ([Stages 05, 07, 13](stages/05-categories-and-templates.md))

| # | Requirement | Why |
|---|---|---|
| T-48 | **Feature-disjointness lint**: an affix whose feature names never overlap any stem's; an affix value with zero stem customers | L-S4-01 (null prefixes over-generating; cl.16) -- **S6-S11:** null-prefix over-generation still present 09-24 .. 09-30 (V-S9-02, V-S10-07, L-S11-03) |
| T-49 | **Slotless-POS lint**: bound stems whose POS has no affix slots | L-S4-04 -- **S6-S11:** related failure: free words blocked because an *ancestor* POS owns a template with obligatory slots (L-S9-01); see T-76 |
| T-50 | **Co-occurring-slot lint**: one MSA in two slots of the same template | L-S5-01 (the two-subject parse) -- **S6-S11:** flag only slots that co-occur in one template; one MSA in Obj and Obj2 is intended (V-S7-09, L-S7-02) |
| T-51 | **Decomposition audit**: lexeme still carries a class prefix; prefix/feature disagreement; compound substrings; TAM or extension baked into a verb | D-S2-05 -- **S6-S11:** run after every lexicon-addition batch: applicative/passive shapes were re-baked into stems after decomposition (C-S7-06, C-S10-03) |
| T-52 | **Parse-ready profile per POS** -- a static readiness check against a declared standard, with an orphan bucket. Extends T-17 | D-S3-03 |

#### P1 -- safer structural writes ([Stage 13](stages/13-cleanup-and-consolidation.md))

| # | Requirement | Why |
|---|---|---|
| T-53 | **Owned-subtree reference check + dangling-analysis sweep**. Extends T-09 | C-S5-01 (`bali` / *alikubali*) |
| T-54 | **`merge_entries(victim, survivor)`** that repoints references and approvals. Different from T-31 | C-S4-03 (merge-by-delete lost approvals) -- **S6-S11:** `ILexEntry.MergeObject` exists and was used raw (T-S7-05); a wrapper is still needed |
| T-55 | **Soft-delete lifecycle**: disable, list with referrer counts, protected-content guard, then delete | D-S4-08 |
| T-56 | **Tiered manifest executor**: GUID-keyed, ordered tiers, live reference re-check, tolerant of already-absent targets. Extends T-35 | D-S5-05, C-S5-02 |

#### P2 -- construction helpers

| # | Requirement | Why |
|---|---|---|
| T-57 | **`clone_slot` / `clone_slot_series(src, dst_pos)` including feature structures**, plus a report of slot optionality shared across templates. Extends T-29 | D-S4-06, L-S5-02 |
| T-58 | **Feature-structure deep-copy and migrate/repoint** (flat to complex value; custom to catalog) | D-S3-01, D-S4-05, C-S3-02 |
| T-59 | **Catalog import of nested EticGlossList items** (flexlibs#192) and a catalog-provenance audit | D-S3-01 |
| T-60 | **Feature-pruning search**: LOCKED/FREE partition plus a uniqueness-preserving removal search. Extends T-27 | D-S3-09 |
| T-61 | **Wrappers** for slots, templates, affix MSAs, null affixes and closed inflection features with values, and **custom-field creation that persists** | C-S1-01, L-S1-01, C-S4-02 -- **S6-S11:** partly met (affix-MSA class change by 09-13, T-S7-05); extend to rule and exception features (C-S10-05, T-72) |
| T-62 | **GUID lookup helpers and stable-id guidance** | C-S1-05, D-S4-07 |
| T-63 | **Guard against accessors that silently return None** | C-S3-03 (flexicon#232) -- **S6-S11:** extend: type-check wrapper arguments and report caller errors as caller errors, not `WrapperInternalError` (T-S11-05, C-S8-01, T-S7-04) |
| T-64 | **Pre-flight false positives** -- they push code into `getattr` obfuscation that defeats the validator | S1, S2 -- **S6-S11:** still open. `partial_module_structure` cost 16 rounds in one day (T-S11-09); discovery state lost on a restart blocked confirmed writes (T-S7-06); weaker clients loop on the gates (T-S6-08, T-S8-08, C-S10-06). As a safety net it worked: it blocked every bad write but one (T-S11-09) |

### Added by the Swahili merge (S6-S11)

S6-S11 are Matthew's logs from the second machine (2026-09-12 .. 09-30). Together with
S1-S5 they cover the Swahili project. S6-S7 logs keep no tool output; S8 (09-23)
onward keep truncated output. Sessions by other clients (local models, an unidentified
weaker client) are counted as tooling evidence, since they show where the tools fail
weaker agents.

**What the shipped parse tools changed.** On 09-30 ten `try_word` / `parse_status` /
`parse_log` calls answered in about two minutes what roughly four hours of
`run_module` scripting had not: all ten "unparsed" target words parsed (T-S11-01,
L-S11-01). One all-texts filing with no grammar change moved "unparsed" from 14,096 to
9,260 (L-S10-01). `parse_diff` gave clean regression verdicts (T-S9-03), and
`parse_sandbox` let a rule edit be tested without touching the project (T-S9-08). The
remaining friction is around the tools rather than in them: locks, morph naming, the
missing per-analysis breakdown, and agents not knowing to use them.

**Defects observed in shipped tools** (bugs to file, not requirements):
- `parse_log` reported "No parse run with handle ..." for `try_word` and diagnostic
  `parse_text` runs listed in `available_runs` (T-S10-04).
- `parse_sandbox create_sandbox` crashed on a missing `scripts/hcparse.ps1` while
  `flextools_health` reported the sandbox ready (T-S10-05).
- A filing run ended `stage: failed` with empty notes (C-S9-05, C-S10-02).
- Flexicon: `GetAllAffixTemplates` items fail the `IMoInflAffixTemplate` cast
  (T-S6-05); `SetMorph` accepts a wrapper it then rejects (T-S7-04).

#### P0 -- the loop, locks and concurrency ([Stage 11](stages/11-parse-and-repair-loop.md))

| # | Requirement | Why |
|---|---|---|
| T-67 | **One writer per project**: a cross-session write lease or queue, plus append-merge (not overwrite) on shared Description and text fields | Two subagents lost commits to `FP_ConflictingSaveError`, and one overwrote another's template description (C-S7-01, T-S7-03); a second client wrote to the same project concurrently (C-S10-06); eight bulk writes ran as a "non-master peer" with FLEx open (C-S8-03) |
| T-68 | **The parse loop reachable by every agent.** Parse tools available to subagents; parser calls inside `run_module` redirected to `try_word` / `parse_text` instead of flagged as unprotected writes | Four subagents wrote grammar blind, "cannot be verified without running the parser", while the main session parsed in-process (T-S7-01, D-S7-02); pre-flight offered only `if modifyAllowed:` for `Parser.TryWord` (T-S11-02) |
| T-69 | **Parse-worker-aware lock handling**: when a write meets `project_locked` held by this server's own idle parse worker, release it (or name it and offer `flextools_parse_release`) | Six `project_locked` rejections right after parse runs; the agent called `parse_cancel` on finished runs and never `parse_release` (T-S8-04, T-S9-05) |
| T-71 | **Post-commit verification by reopen** after any teardown warning, reported in the same response | A rule disable read back "True" inside the op and never persisted; "writes may not have been committed" was undecidable without a reopen (C-S9-02, T-S9-06). Extends T-08 |
| T-73 | **Filing as a human gate with reasons**: a filing confirmation separate from `write_enabled`, scope shown in tokens and analyses at risk, and a failure reason on `stage: failed` | A 26,725-word filing was self-confirmed 21 s after its preview (C-S10-02); Matthew later withheld filing explicitly (D-S10-04); failures returned no reason (C-S9-05) |

#### P1 -- diagnosis and lints ([Stages 05, 07, 08](stages/05-categories-and-templates.md))

| # | Requirement | Why |
|---|---|---|
| T-70 | **Morph resolution for restricted `try_word`**: resolve a piece by lexeme, citation or allomorph form, and on `parse_morph_unresolved` return candidate headwords with homograph numbers and morph-type markers | `ake`, `*ake`, `mi`, `mi-`, `roho` all failed with `candidates: []`; the real headwords were `mi-1`, `*aka`, `*roho` (T-S8-02, T-S9-02, T-S10-01). Extends T-02, T-33 |
| T-72 | **Phonological-rule and exception-feature wrappers**: enable/disable a rule or one RHS, set required/excluded features, create rule and exception features, tag entries | Disabling a rule failed through raw casts and never persisted (T-S9-07); an exception feature took four failed raw-LCM attempts (C-S10-05). Extends T-30, T-61 |
| T-74 | **Unslotted-inflectional-affix lint** (a `grammar_health` candidate) | An inflectional MSA with no slot is tried in every position; a hand-built audit caught 14 in its own dry run (D-S8-08, T-S8-07). Sibling of T-49, T-50 |
| T-75 | **Gloss/feature consistency lint**: a gloss naming N agreement values over an MSA that encodes fewer | `conn.conc.nc4/6/9` carried class 4 only, so the other classes silently failed to unify (L-S8-03, D-S8-07) |
| T-76 | **Template-reachability lint**: a POS that inherits an obligatory-slot template from an ancestor; template filler MSAs whose POS is neither the template's POS nor an ancestor (inert template) | Pronouns, `amba-` relatives and invariant numerals failed through an ancestor's template; fixing that unblocked about 3,000 tokens (L-S9-01 .. L-S9-03). An inert Quantifier template (L-S7-04). Extends T-49 |
| T-65 | **`swap_lexeme_with_allomorph(entry, allomorph)`** with a reference-integrity check (morph-bundle references before and after) | Hand-ported from FieldWorks' `SwapAllomorphWithLexeme` and applied to 20 entries; a guessed API (`ReplaceMoForm`) left an orphan in the work project first (T-S6-03, D-S6-05, C-S6-01). Sibling of T-31 |

#### P2 -- observability and agent guidance

| # | Requirement | Why |
|---|---|---|
| T-66 | **Per-operation provenance**: an agent/subagent/batch id on every op, and `user_request` refreshed to the latest operator turn (never a subagent prompt or the agent's intent) | Parallel subagents logged under one session id and one request (T-S6-07, T-S10-08); the request field froze at the first message or copied the intent (T-S8-06, T-S9-09), so the operator's instructions cannot be recovered from the log |
| T-77 | **Repeated-failure circuit breaker**: on the second identical error signature, say so and suggest a different approach or escalation | 16 identical `'str' object has no attribute 'Form'` failures in 11 minutes, 5 `IStTxtPara`, 6 `unprotected_writes` (C-S11-07, T-S11-09) |
| T-78 | **Casting checker aware of Flexicon return types**; index `ParseResult` | Advice to cast a Flexicon `ParseResult` to `IStTxtPara` blocked a run and led to five failing retries (T-S11-04) |

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

**Progress after the S1-S5 partial merge:**

| Step | Status |
|---|---|
| 1. Directive index | Done for S1-S5 |
| 2. Stages vs his workflow | Done as per-stage evidence sections. No renumbering was needed: his work fits the 13 stages, with 10/12 merged and Stage 11 extended |
| 3. Matthew's-choice column | Done as section 1b plus rows 25-31 |
| 4. Re-open conflicts | Done: README 4.9-4.15 |
| 5. Split reference/ | Done: `swahili-morphophonology.md` added; language-neutral items promoted to rows 25-31 |
| 6. Guardrails by rule | Done: confirmation table plus section K |
| 7. Open questions | Partly: Q-12 answered for Swahili; Q-06 not tested; Q-16/21/23/27 annotated; Q-37-Q-42 added |
| 8. Tooling backlog | T-44 to T-64 added; existing items annotated |
| **Remaining** | Ingest the other machine's logs (S6 onward); re-check everything marked *inferred* |
