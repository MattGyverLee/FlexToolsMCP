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
  solved in a session not in this corpus). Stage 11 was written for in-MCP tooling that
  did not exist yet.
  *Status 2026-10-09: that tooling now exists. The parse tools landed 09-18..09-24 and
  first shipped in FlexToolsMCP 2.13.0 (2026-09-25): `flextools_grammar_health`,
  `try_word`, `parse_status`, `parse_text` (with filing), `parse_log`, `parse_diff`,
  `parse_cancel`, `parse_release`, `parse_sandbox`. Ron's sessions (09-10..15) predate
  all of them, so "out of band" stays true for his corpus. Matthew used them from
  09-23 (S8-S11).*

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
  [open-questions](open-questions.md) Q-37 to Q-42 (S1-S5) and Q-43 to Q-51 (S6-S11).
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

- **Transcript check done (2026-10-09).** S6-S11 were re-checked against the Claude Code
  transcripts behind those sessions, with Matthew's permission. They supply the output the
  pre-09-23 logs lack, Matthew's verbatim words, and 92 new ids. Biggest corrections:
  `DoNotUseForParsing` is a no-op in both parsers; most 09-13 grammar writes were
  parse-checked (HermitCrab in-process, or Matthew's own FLEx screenshots); overnight
  agents ran sequentially, not in parallel; several decisions credited to the AI were
  Matthew's; the 09-30 junk entries (9) were committed.
- **No transcript** for 09-13 14:09-20:05, 09-14, the local-model and hermes sessions,
  the 09-25 second client, 09-25 16:36-17:22 and 22:39-23:32, or 09-30 (client
  unidentified). Results there remain log-only.
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
Rows marked **S6-S11:** carry status evidence from those logs. The logs label the
server "2.12.0", but the parse tools were not in 2.12.0: S8-S11 ran a pre-2.13.0 main
checkout (try_word on main 09-20, filing and sandbox 09-24; first release 2.13.0,
2026-09-25). The **Status (2026-10-09)** column reconciles each row against
FlexToolsMCP `main` (cee5a84; released 2.15.0, 2026-10-04) and flexicon `main`
(released 4.12.0, 2026-10-02), and the Why cells were corrected where the Claude Code
transcripts behind S6-S11 refute the logs. Where a Why cell says "still open" and the
status column disagrees, the column is current. Summary in
[Fix status (2026-10-09)](#fix-status-2026-10-09) below.

Priority reflects how often the corpus hand-rolled the capability and how much damage
its absence caused.

### P0 -- the parsing loop itself ([Stage 11](stages/11-parse-and-repair-loop.md))

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-01 | **`parse_text(text)`** in-band: per wordform, analysis count and per analysis the full morpheme breakdown (entry, allomorph, slot, MSA), plus timing | Parse results were exchanged out of band and are **not recoverable from the logs** (M5 §7) -- **S6-S11:** partly met. `parse_text` parses word lists and corpus scopes in-band and files results. Its response, and `try_word`'s, carry counts only. The breakdown was on disk all along (run records, `parse_log section=results`, since CP3 09-22), but no agent read it: they read stored (possibly stale) bundles (T-S10-03), shell-scraped the 138 KB trace XML (T-S8-03), or, on 09-30, invented a decomposition table (D-S11-04, C-S11-08) | **Partial (doc was inaccurate).** `parse_log section=results` gives each analysis's `rendered_morphs`, `category_labels`, `morph_glosses`, `entry_guids`, `morph_kinds` and `parse_time_ms` since c046f56/c5a1924 (09-22, released 2.13.0). Gap: not in the try_word/parse_text response, and no slot |
| T-02 | **`explain_parse_failure(surface_form)`** -- how far the parser got: which stem allomorph matched, which suffix was attempted, which environment or inflection-class restriction rejected it, which rule did or did not apply | The single highest-value missing tool. Every diagnostic operation in M1, M2, M3, M5, M8 is a hand-rolled partial version of it -- **S6-S11:** partly met by the `try_word` ladder (`restricted` tests a stated decomposition; `explain` writes a trace) plus `parse_log` section=trace, a rejection histogram with the first failing rule (T-S9-01, T-S11-01). The reason stays in the trace, not the response; `restricted` needs exact headwords (T-70) | **Partial.** `try_word level=explain` trace + `parse_log section=trace` summary and `rejections_by_type`; no prose explanation |
| T-03 | **`parse_diff(prev_run, cur_run)`** -- newly failing / newly passing / changed analysis count | D-M3-01's mandatory regression check, currently manual -- **S6-S11:** met by `flextools_parse_diff` ("fixed 3, broken 0", T-S9-03); not used in a grammar-wide stage whose agent wrote its own baseline and diff scripts instead (T-S10-07, confirmed by transcript) | **Shipped:** `flextools_parse_diff` (81324e7, 09-22; released 2.13.0) |
| T-04 | **Automatic bucket partition** (zero / one / duplicate-signature multi / distinct-signature multi), grouping multi-analyses by morpheme signature | Mechanizes D-M3-04's duplicate-vs-genuine-ambiguity distinction -- **S6-S11:** partly met, not used. Filed analyses over-generate unnoticed (Misri 10, mwana 13; L-S10-05) | **Partial (doc was inaccurate).** CP3 batch signals since c5a1924 (09-22): `analyses_per_word`, `root_entry_disagreement`, `root_as_affix_stack`, `incompatible_categories`, `analysis_count_distribution`, plus `signals/clustering.py`. No zero/one/duplicate/distinct partition by morpheme signature |
| T-05 | **Parse-run persistence** so runs can be diffed and failure lists are not lost | M5 §7 item 4 -- **S6-S11:** met with defects. Runs persist by id from 09-24, but `parse_log` could not find `try_word` runs `parse_status` had just reported (T-S10-04, log evidence only), and traces were pruned (T-S9-01); the S10 lex-parser agent copied traces out for that reason (D-S10-12) | **Shipped, with an open defect.** Run records on disk, newest 20 runs per project kept (`parse/retention.py`). The `parse_log` handle bug is open and not filed. Probable cause (unverified): `_run_not_found` lists the runner's in-memory `known_run_ids()`, while `_log_record` needs the record on disk, which retention may already have pruned |
| T-06 | **`parse_forms([...])`** -- parse an ad hoc list without creating a text | Hypothesis testing during repair -- **S6-S11:** met by `try_word` and word-list `parse_text` (T-S8-01, T-S11-01); most single words return an async handle to poll (T-S10-02). Hand-driven HermitCrab inside `run_module` came first (T-S7-01, 09-13 from about 01:57) | **Shipped:** `parse_text scope_kind="words"`, `parse_sandbox action=parse`, `try_word` (9cb8af6/c046f56, 09-20/22; released 2.13.0). The async handle is by design |
| T-07 | **Parse timing per run and per word, diffed against the previous run** | D-M3-02 made parse time a first-class metric; it was measured by stopwatch -- **S6-S11:** partly met. Per-word time is visible through polling (5-40 s); about 3.2 s/word in the S10 Stage 2 baseline (transcript), and both 1,783- and 1,610-word baselines died at word 173 when the MCP server restarted (D-S10-05); no per-run timing diff (T-S10-02) | **Partial.** Per-word `parse_time_ms`; `try_word bound_seconds`; parse-tool durations in operations.jsonl (CP6, 0c4e488, 09-28); `parse_diff` does not compare timing |

### P0 -- the atomicity gap ([Stage 06](stages/06-stem-and-affix-population.md), [Stage 13](stages/13-cleanup-and-consolidation.md))

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-08 | **A transactional / rollback-capable write mode** | Three shards record: "the atomicity unit for this whole session is the SESSION, not the operation" (M5 §6, M6 §6, M8 §6). It directly caused half-built entries (C-M6-02). Most of the conventions in [flex-data-conventions §6](conventions/flex-data-conventions.md) are mitigations for its absence -- **S6-S11:** still open. `undoable=False` left an orphan after a failed delete (T-S6-04); a rule disable never persisted while lexical writes in the same window did (C-S9-02, T-S9-06); 09-20 and 09-12 partial writes ran under `undoable=False` (C-S8-05, T-S8-11, T-S7-09). On 09-30 a script that raised still committed 9 bare entries, because the runner's `finally` closes (saves) the project, and the error response dropped the script's messages (C-S11-05, T-S11-10). Filing alone has preview, confirm and backup (T-S10-06). See T-71 | **Partial.** Per-operation units of work restored in the runner (#144, 0d3a791, 09-18, released 2.13.0) on flexicon 4.4.0's UoW; a script can group its own writes with `with project.UndoableOperation(...)` (rollback caveat documented, flexicon#579). A failed run now returns its messages (#347, 2.15.0). Still: a script that raises keeps the operations it completed, and there is no session-level transaction. The S4-S9 evidence predates 2.13.0 |
| T-09 | **A guarded bulk-delete primitive**: requires an explicit target list, or a predicate **plus** a category filter; refuses senseful items by default; backs up content; writes a log; replayable in reverse | C-M7-01 (92 + 6 wrongly deleted), D-M5-10, D-M7-02 | **Partial.** Automatic pre-write backup + `confirmation_required`; recipe `delete-variant-entries-by-type` skips senseful entries; no general guarded-delete primitive, no reverse replay |

### P1 -- blast-radius and lint tools ([Stages 04, 07, 08](stages/04-natural-classes.md))

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-10 | **`referrers_of(class \| environment \| inflection_class \| stem_name \| feature)`**, surfaced **automatically** on any write touching a shared object | C-M5-05 -- the corpus's most expensive class-related mistake | **Open.** No referrer API in flexicon or the MCP |
| T-11 | **`restriction_impact(allomorph, proposed_classes)`** -- which entries would be excluded | C-M5-06 (over-narrowing broke a sibling class) | Not assessed (not in the fix ledgers) |
| T-12 | **Unanchored-context lint**: "rule R has an RHS whose context is a bare natural class with no boundary marker" | A one-line static check that would have prevented a 4-minute corpus parse time (L-M3-02) -- **S6-S11:** `grammar_health` now scans for path-multiplying properties (representation-variant product 1.8e10, T-S10-02); whether it includes this lint was not exercised | **Open.** Not a `grammar_health` check (nearest: `unbounded-quantifier`, `epenthesis-empty-struc-desc`) |
| T-13 | **Allomorph-representation lint**: entries mixing plain and process alternates; unreachable citation forms; allomorphs identical to their entry's lexeme form; environments whose string is empty | C-M1-05, C-M1-06, L-M3-05, L-M8-04 -- **S6-S11:** add two checks -- a lexeme form that is conditioned while an alternate is unconditioned ("swapped", T-S6-06, L-S6-01), and environment-less allomorph lists holding derived stems (L-S10-04) | **Partial (recipe level).** Recipe `overpowered-allomorphs` (af8e97d, 09-28, 2.15.0) flags unconstrained allomorphs and abstract lexeme forms paired with non-abstract allomorphs; no "swapped" lint and no `grammar_health` check |
| T-14 | **Inflection/derivation lint**: warn when a template-slotted affix's MSA changes the part of speech | C-M6-03 | **Open** (not in the fix ledgers; no matching `grammar_health` check found) |
| T-15 | **Writing-system lint on environment strings** | D-M3-05 ("otherwise I get boxes") | **Open** (not in the fix ledgers; no matching `grammar_health` check found) |
| T-16 | **Duplicate-object detection** across classes, environments and possibility items | D-M5-05, D-M7-05 | **Partial.** Recipe `case-duplicate-entries`; `grammar_health` `duplicate-feature-bundle`; nothing for environments or possibility items |
| T-17 | **Required-fields lint**: entries missing a WS form, gloss, sense, or POS | D-M2-03 | **Partial.** Recipe `publication-readiness-check` (no gloss/definition, placeholder POS) only |

### P1 -- coverage and redundancy reports

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-18 | **`environment_coverage_report(texts)`** -- for each allomorph and environment, does any test wordform exercise it? A **test-coverage report for a grammar** | D-M2-06's sampling criterion, never measured (Q-22) | **Open** |
| T-19 | **`allomorph_usage_report()`** -- usage count per stored allomorph across all analyses | M1 op 41, hand-rolled -- **S6-S11:** still missing; hand-rolled six times in one session (T-S6-06), and it found the shadowed allomorph (m-3 `mw` used 0 times, its siblings 1-8 times; L-S6-01) | **Open.** Nearest: per-entry recipe `form-usage-before-edit` (af8e97d, 09-28); no project-wide report |
| T-20 | **`redundancy_report()`** -- rule-derivable allomorphs, lexeme-form clones, zero-usage allomorphs, duplicate possibility items, orphaned contexts, zero-referrer classes | M1 op 35, L-M3-05, Stage 13 | **Partial.** Audit recipes `overpowered-allomorphs`, `prune-citation-forms-matching-lexeme`, `find-overpowered-affixes`; no single report |
| T-21 | **`convention_audit(phenomenon)`** -- how many entries use representation A, how many B, how many both | L-M6-01, counted once and never resolved (Q-04) | **Open** |
| T-22 | **Over-generation probing**: generate what the grammar permits for a paradigm and diff against attested cells | D-M8-05 was found by reasoning; bucket D is otherwise invisible (Q-25) -- **S6-S11:** still missing. Manual substitute: Matthew's "No Parse" genre (D-S7-08): 69 hand corrections and 537 verb forms moved into texts of forms judged ungrammatical. They were never parsed, and by the AI's own answer most would parse, wrongly (C-S7-11). Label such a set "ungrammatical (hand-judged)", not "fails to parse". Generate through the grammar, not by string concatenation (C-S7-05) | **Open.** Nothing in either repo; `parse_diff`'s `changed` bucket shows loosening on attested words only |
| T-23 | **`failures_to_candidates(parse_run)`** -- deduplicated, normalized candidate list with a category guess | D-M8-04, built by hand each round -- **S6-S11:** still missing; the frequency queue was hand-rolled four times in one day and only one was right (T-S11-06). Matthew asked twice for a reparse of exactly the zero-count queue (D-S8-18, 09-23; D-S11-06, 10-02); on 10-02 it still took two calls | **Partial.** Recipe `parser-coverage` ("most frequent unparsed wordforms", af8e97d, 09-28) existed but was not surfaced until #335 (cbd2050, 10-02, 2.15.0), so the 09-30 client never found it. Nothing builds candidates from a parse run |
| T-24 | **Coverage statistics per run** (token, type, frequency-ordered failures) | Stage 12 work queue ordering -- **S6-S11:** still missing, and needs one definition of "unparsed": three gave 14,096 / 9,066 / 0 on one day (T-S10-09), and on 09-24 the count read 14,038 -> 14,006 -> 13,927 (in texts) then 14,105 (all wordforms) as the definition changed, not the grammar (T-S9-11) | **Partial.** Type-level `NumWords` / `NumZeroParses` per `parse_text` run, occurrence-ordered; `parser-coverage` fixes one stored definition (in texts, `ParserCount > 0`, `GetOccurrenceCount`); flexicon `GetParserCount`/`GetUserCount`/`IsParsed` (#576, 4.12.0). No token coverage, no per-run statistics |

### P2 -- construction and survey helpers

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-25 | **`survey_project()`** -- whole pre-state in one call; plus **`diff_snapshot()`** | Every shard opens by re-writing the same survey code; C-M2-06 would have been resolved in seconds | **Open.** Inventory recipes only; `parse_diff` diffs parse output only |
| T-26 | **`verify_inventory_covers(text_or_wordlist)`** -- decompose and report undefined graphemes | Stage 02, done by hand every time -- **S6-S11:** cheap variant: parse rate per grapheme (gh 7%, th 17% vs 66% overall; D-S10-06) | **Open.** No inventory check and no per-grapheme parse rate |
| T-27 | **`assign_feature_matrix(table)`** with the distinctiveness + minimality proof as a **refusal gate**; plus `diff_feature_matrix(table)` | D-M1-04, D-M1-06 | **Partial.** Read-only recipe `phoneme-feature-uniqueness`; no assign/refusal gate |
| T-28 | **`propose_natural_classes()`** -- cluster identical conditioning sets, report sharing counts and feature-definability; **`check_class_distinguishability(members)`** | D-M3-05's threshold test; L-M7-03's failure | Not assessed (not in the fix ledgers) |
| T-29 | **`clone_template(from_pos, to_pos)`** | D-M8-03's build-by-analogy | **Partial.** flexicon `MorphRules.Duplicate(template, deep=True)` within one POS; no cross-POS clone |
| T-30 | **Affix-process rule construction as one call**, with factory-seeded-node cleanup and well-formedness validation | M7 ops 19-20 -- **S6-S11:** still open; see T-72 for rule enable/disable and exception features | **Open.** No `MoAffixProcess` builder |
| T-31 | **Variant-vs-allomorph conversion primitive**, both directions | Done, reverted, then bulk-applied 101 times across the corpus | **Open** |
| T-32 | **`rule_derives(rule, input)`** -- apply one rule in isolation without a full parse | The corpus had no way to test a rule except by parsing -- **S6-S11:** met in spirit by `parse_sandbox` (T-S9-08): a 2,139-word A/B with the glide rule removed finished at 1,517 -> 1,568 parsed, 54 fixed, 3 broken (transcript). It crashed on an unreadable `hcparse.ps1` on 09-25 22:54 (T-S10-05), possibly after that morning's broken editable reinstall (T-S10-12, unproven) | **Partial.** `parse_sandbox` (2.13.0) tests an edited grammar copy on whole words; no single-rule application, no XML-edit helper, no write-back. The script is package data since 06f90a8 (09-24); an unreadable script now returns `sandbox_unavailable` (#322, PR #361, 01f5d0e, 2.15.0) |
| T-33 | **`explain_allomorph_selection(entry, surface_form)`** | The write-side counterpart of T-02 | **Partial.** `try_word level=restricted` + explain trace |
| T-34 | **`why_didnt_this_compound(form)`** | M6 op 30, asked by hand and left unanswered (Q-10) | **Open.** Generic explain trace only |
| T-35 | **`reconcile_import(plan)`** -- present / missing / present-but-incomplete | D-M5-13 | Not assessed (not in the fix ledgers) |
| T-36 | **Recursive possibility-list resolution** as a first-class helper | C-M6-02 | **Partial.** `POS.Find`, `PossibilityLists.FindItem` recurse; variant `FindType` (one level) and generic list wrappers do not; a None argument now raises before any write |
| T-37 | **Polymorphic-safe allomorph read/write wrappers** (stem vs affix subtype) | C-M1-02, C-M2-01 -- **S6-S11:** open at the time (T-S6-05, T-S9-10); flexicon#449 was filed from the 09-24 session at Matthew's "write P0 issues for all 3" (D-S9-09). Reading `SlotsRC` needs a cast to `IMoInflAffMsa` (T-S7-08) | **Fixed.** `GetForm` ClassName dispatch (df37e35, 09-07); `GetAll()` wrappers unwrapped before the cast (#449, 4.10.0); #599 closed as not reproducible and locked by tests (4.12.0). Morph-type name reader `GetMorphTypeName` (#583, 4.12.0) |
| T-38 | **Automatic citation-form population** for affix entries | M7 §6 ("-???" display) | **Open** (automation); manual `LexEntry.SetCitationForm` exists |
| T-39 | **Enclitic "attaches to" helper** | M2 §6 -- no wrapper exists, raw LCM required | **Open.** No `FromPartsOfSpeechRC` wrapper; no issue filed |
| T-40 | **Category-name registry** so creation and consumption cannot diverge | C-M5-01 (69/69 rows failed) | **Open** |
| T-41 | **Surface the FLEx "apply rules to clitics" setting** through the MCP | D-M3-03 -- a data-level diagnosis chasing an application-level cause | **Open.** Parser parameters are echoed only in `try_word bound_seconds` results |

### P2 -- observability

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-42 | **Overflow-safe output**: spill large report payloads to a file automatically | M8 §6 (320 messages truncated to 100) -- **S6-S11:** still open as a default (14,284 rows capped to 100, T-S8-05; T-S7-02) | **Partial.** Default cap still 100; an in-band marker (`summary.info_truncated`) and the `max_info_messages=0` opt-out exist since MCP#25/#43 (05-30 / 07-01); no automatic spill to file, no issue filed |
| T-43 | **Persist report output in the operation log**, not only source code and message counts | This is why Q-08, Q-13, Q-17, Q-20 are open at all. The log format is the reason several conclusions in this corpus are unrecoverable -- **S6-S11:** partly met from 09-23 -- output is logged but truncated at about 1-2 KB (T-S9-09, T-S10-06, T-S11-07). S6-S7 logs kept counts only (T-S6-01, T-S7-02). The agents did see the full output (the transcripts quote it); only the log lost it. Operator messages typed mid-turn never reach the log at all (T-S9-09, S8 transcript) | **Open, not filed.** `[OUT]` keeps 1000 chars per result (`server.py`, unchanged since 4dfa820, 04-07); report.Info is logged in full only on failed runs; parse runs persist in their own records (newest 20) |

### Added by the Swahili partial merge (S1-S5)

**Confirmed by S1-S5:**

- **T-43** (report output not persisted): confirmed in every Swahili shard. It is the
  reason most Swahili results are inferred.
- **T-08** (atomicity): C-S1-01, C-S4-02, C-S5-03.
- **T-09** (guarded bulk delete): C-S1-02, C-S5-01.
- **T-01** (in-band parse): the GUI parser was run at the keyboard.
- **T-22** (over-generation probing): L-S4-01 is a mechanizable case.
- Also confirmed: T-10, T-16, T-17, T-19, T-20, T-23, T-24, T-25, T-27, T-30, T-37.

The in-band parsing tools have since shipped (FlexToolsMCP 2.13.0, 2026-09-25). Their
status as observed in S6-S11 is given inline on each row (**S6-S11:**) and in the
S6-S11 subsection below; the current status is in the Status column.

#### P0 -- the analysis layer ([Stage 11](stages/11-parse-and-repair-loop.md))

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-44 | **Approve / reject analysis with agent and reason**, recorded and queryable | Approve/reject wrappers failed silently. Raw `ICmAgent.SetEvaluation` was needed, and a heuristic was recorded as Human (C-S2-01, D-S4-02) -- **S6-S11:** partly met. Filing through `parse_text` records parser evaluations only, never Human (T-S9-04). Approve/reject with reason is still missing; a count by display name misread parser approvals as human (C-S9-03) | **Partial.** flexicon `SetApprovalStatus` persists (flexicon#24/#26/#56); `WfiAnalysis.GetEvaluationsForAgent`/`ClearEvaluation`/`RemoveAllHumanEvaluations` (#582, 4.12.0) and recipe `remove-user-analyses`; `ApproveAnalysis`/`RejectAnalysis` still take no agent or reason and always write the human agent; filing records the parser agent |
| T-45 | **`analyses_violating_grammar()`** -- stored analyses whose slot sequence the current templates forbid | D-S5-03; stale analyses also caused a misdiagnosis (C-S2-05) | **Partial.** Per-word human-vs-parser oracle in the `parse_text` report; no project-wide query |
| T-46 | **`slot_usage_report()`** -- per-slot usage across all analyses (the slot twin of T-19) | D-S4-04's "ZERO analyses project-wide" test | **Open** |
| T-47 | **Interlinear helpers**: pick an analysis by morph signature, link senses, set the word gloss, approve, point a token at an analysis, hand-build an analysis; mixed-WS paragraph creation and a per-run WS read | D-S5-06, D-S5-08, C-S5-03 | **Partial.** `Segments.SetAnalysis`, `WfiGlosses.Create`, `WfiAnalysis.Create/AddGloss`; no mixed-WS paragraph creator, per-run WS read or pick-by-signature |

#### P1 -- lints ([Stages 05, 07, 13](stages/05-categories-and-templates.md))

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-48 | **Feature-disjointness lint**: an affix whose feature names never overlap any stem's; an affix value with zero stem customers | L-S4-01 (null prefixes over-generating; cl.16) -- **S6-S11:** null-prefix over-generation still present 09-24 .. 09-30 (V-S9-02, V-S10-07, L-S11-03); every 9/10 noun gets two look-alike analyses, null nc9 and null nc10 (L-S11-04). The cl.16 null prefix was never suppressed: `DoNotUseForParsing` is a no-op in both parsers (S10 transcript; refutes V-S7-02) | **Partial (recipe level).** Recipe `find-overpowered-affixes` (af8e97d, 09-28) flags null-form allomorphs in optional slots; no feature-disjointness lint |
| T-49 | **Slotless-POS lint**: bound stems whose POS has no affix slots | L-S4-04 -- **S6-S11:** related failure: free words blocked because an *ancestor* POS owns a template with obligatory slots (L-S9-01); see T-76 | **Open** (not in the fix ledgers; no matching `grammar_health` check found) |
| T-50 | **Co-occurring-slot lint**: one MSA in two slots of the same template | L-S5-01 (the two-subject parse) -- **S6-S11:** flag only slots that co-occur in one template; one MSA in Obj and Obj2 is intended (V-S7-09, L-S7-02) | **Partial (recipe level).** Recipe `find-overpowered-affixes` flags one affix entry in two or more prefix slots of a template; not a `grammar_health` lint, and it does not exempt the intended one-MSA-two-slots idiom |
| T-51 | **Decomposition audit**: lexeme still carries a class prefix; prefix/feature disagreement; compound substrings; TAM or extension baked into a verb | D-S2-05 -- **S6-S11:** run after every lexicon-addition batch: applicative/passive shapes were re-baked into stems after decomposition (C-S7-06, C-S10-03) | **Open** (not in the fix ledgers; no matching `grammar_health` check found) |
| T-52 | **Parse-ready profile per POS** -- a static readiness check against a declared standard, with an orphan bucket. Extends T-17 | D-S3-03 | **Partial.** As T-17; no per-POS parse-ready lint |

#### P1 -- safer structural writes ([Stage 13](stages/13-cleanup-and-consolidation.md))

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-53 | **Owned-subtree reference check + dangling-analysis sweep**. Extends T-09 | C-S5-01 (`bali` / *alikubali*) | **Partial.** Run recipe `form-usage-before-edit` before a delete; no dangling-analysis sweep |
| T-54 | **`merge_entries(victim, survivor)`** that repoints references and approvals. Different from T-31 | C-S4-03 (merge-by-delete lost approvals) -- **S6-S11:** merge used on 09-13 at Matthew's "merge the 2 mu entries" (T-S7-05); FLEx collapsed the two MSAs during the merge, and ambiguity tracks MSAs, not senses (L-S7-19) | **Mostly fixed (doc was inaccurate).** The wrapper already existed: `LexEntry.MergeObject(survivor, victim, fLoseNoStringData, auto_deduplicate)` (ab7cd40b, 2025-12-05) delegates to `ILexEntry.MergeObject`. Survival of analyses and approvals unverified |
| T-55 | **Soft-delete lifecycle**: disable, list with referrer counts, protected-content guard, then delete | D-S4-08 | **Superseded.** `DoNotUseForParsing` never affected HermitCrab or XAmple (they skip only `IsAbstract` forms; HCLoader.cs:543/585), so every S4-S8 suppression with it was a no-op. Refused at preflight with `deprecated_member` since 2.13.0 (a40e250, PR #259); soft-disable with `IsAbstract` on the lexeme form and every allomorph (recipe `hide-entry-from-parser`, flexicon `Get/SetIsAbstract` #546); upstream LT-22810 under a weekly watch. No lifecycle tool |
| T-56 | **Tiered manifest executor**: GUID-keyed, ordered tiers, live reference re-check, tolerant of already-absent targets. Extends T-35 | D-S5-05, C-S5-02 | **Open.** A stale GUID now raises `FP_ParameterError` from `project.Object()` (flexicon#262) |

#### P2 -- construction helpers

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-57 | **`clone_slot` / `clone_slot_series(src, dst_pos)` including feature structures**, plus a report of slot optionality shared across templates. Extends T-29 | D-S4-06, L-S5-02 | **Open** |
| T-58 | **Feature-structure deep-copy and migrate/repoint** (flat to complex value; custom to catalog) | D-S3-01, D-S4-05, C-S3-02 | **Partial.** `MSA.GetFeatures` + `MakeFeatStruc` read and rebuild; no copy/migrate helper |
| T-59 | **Catalog import of nested EticGlossList items** (flexlibs#192) and a catalog-provenance audit | D-S3-01 | **Fixed** (import, flexlibs#192, 2026-06-21); **open** (provenance audit) |
| T-60 | **Feature-pruning search**: LOCKED/FREE partition plus a uniqueness-preserving removal search. Extends T-27 | D-S3-09 | **Open** |
| T-61 | **Wrappers** for slots, templates, affix MSAs, null affixes and closed inflection features with values, and **custom-field creation that persists** | C-S1-01, L-S1-01, C-S4-02 -- **S6-S11:** partly met (Infl->Deriv class change via `ChangeAffixVariant` by 09-13 02:10; the reverse needed the raw factory, T-S7-05; a new affix entry needed manual MSA wiring, T-S7-10); extend to rule and exception features (C-S10-05, T-72) | **Mostly fixed in flexicon.** Slots/templates 4.10.0 (`POS.CreateAffixSlot`, `MorphRules.AddSlotToTemplate`); slot readers and `AffixSlot` (#542, 4.11.0); MSA and allomorph inflection classes, required features, template reorder (#573, #580, #581, 4.12.0); affix MSAs, closed features with values; null affixes: empty form refused by design, write `∅`. Exception features: see T-72. Custom-field creation still refused (create in the FLEx GUI; peer-written custom fields are lost) |
| T-62 | **GUID lookup helpers and stable-id guidance** | C-S1-05, D-S4-07 | **Partial.** `project.Object(guid)` raises on stale GUIDs (flexicon#262) but returns an uncast `ICmObject`; documented in the runtime primer (MCP#348, 2.15.0) |
| T-63 | **Guard against accessors that silently return None** | C-S3-03 (flexicon#232) -- **S6-S11:** extend: type-check wrapper arguments and report caller errors as caller errors, not `WrapperInternalError` (T-S11-05, C-S8-01, T-S7-04) | **Partial.** flexicon#232 fixed (4.4.0) plus sibling sweeps; wrong-type arguments raise `FP_ParameterError` (flexicon#600, filed from the 09-30 loop, and the #618 resolver sweep, 4.12.0). Open on the MCP side, not filed: the classifier (`handlers/execution.py`) still labels any other AttributeError raised inside flexicon `WrapperInternalError` |
| T-64 | **Pre-flight false positives** -- they push code into `getattr` obfuscation that defeats the validator | S1, S2 -- **S6-S11:** still open. `partial_module_structure` cost 16 rounds in one day (T-S11-09); discovery state lost on a restart blocked confirmed writes (T-S7-06); weaker clients loop on the gates (T-S6-08, T-S8-08, C-S10-06). As a safety net it worked: it blocked every bad write but one (T-S11-09; 09-30: about 65 real runs, 15% ok, 55% preflight rejects; FlexToolsMCP#334 filed that evening) | **Largely fixed.** `partial_module_structure`: code with `def Main` runs as a snippet (#303, 98b6c40, 09-30) and identical resubmits are caught (#334); other false positives #278, #308, #311, #305/#304, #351/#352, #319, #316; inline discovery recorded (#340); all in 2.15.0 except #278 (2.14.0). Discovery state still is not persisted across a restart (documented, #349); mitigations `FLEXTOOLS_STATELESS` (#142) and read-only auto-grant (#244) |

### Added by the Swahili merge (S6-S11)

S6-S11 are Matthew's logs from the second machine (2026-09-12 .. 09-30). Together with
S1-S5 they cover the Swahili project. S6-S7 logs keep no tool output; S8 (09-23)
onward keep truncated output. Sessions by other clients (local models, an unidentified
weaker client) are counted as tooling evidence, since they show where the tools fail
weaker agents.

**What the shipped parse tools changed.** On 09-30 ten `try_word` / `parse_status` /
`parse_log` calls answered in about two minutes what roughly four hours of
`run_module` scripting had not: all ten "unparsed" target words parsed (T-S11-01,
L-S11-01). They parsed because the S10 Stage 1 agent had fixed them on 09-25 and
filing was deferred to a Stage 5 that never ran (V-S11-04). One all-texts filing with
no grammar change moved "unparsed" from 14,096 to 9,260 (L-S10-01: 10,299 analyses
created, 21,959 re-approved, 322 deleted). `parse_diff` gave clean regression verdicts
(T-S9-03), and `parse_sandbox` ran a 2,139-word A/B rule test without touching the
project (T-S9-08). The remaining friction is around the tools rather than in them:
morph naming, the breakdown being on disk rather than in the response, and agents not
knowing to use the tools. Locks were the other big one; that is fixed (T-69).

**The parse tools grew out of these sessions.** Several fixes were built the same day
as the event that exposed them: Matthew had the 09-24 13:59 P0s filed (#223, flexicon
#448, #449; D-S9-09), and `flextools_parse_release` landed at 15:41 (#225), partly to
his design ("the parser works off of a cached copy of the grammar", D-S9-10). The
09-24/25 filing failure became #239 and was fixed by #240 that night (T-S10-10); the
3.4 MB filing preview became #252 (T-S10-11); the 09-30 loops became FlexToolsMCP
#334, #335 and flexicon#600, and #306 was fixed by PR #338 the same evening. So
"never offered `parse_release`" (T-S8-04, T-S9-05) means it did not exist yet.

**Defects observed in shipped tools** (status 2026-10-09):
- `parse_log` reported "No parse run with handle ..." for `try_word` and diagnostic
  `parse_text` runs listed in `available_runs` (T-S10-04, log evidence only).
  *Open, not filed -- file it. Probable cause (unverified): `_run_not_found` lists
  the runner's in-memory `known_run_ids()`, but `_log_record` needs the record on
  disk, and the 20-run retention (`parse/retention.py`) may already have pruned it.
  Code unchanged since c046f56 (09-22) apart from the 58f196b split.*
- `parse_sandbox create_sandbox` crashed on an unreadable `scripts/hcparse.ps1`
  (`HcparseVersionError`, 09-25 22:54) while `flextools_health` reported the
  sandbox ready (T-S10-05).
  *Crash fixed: the script is package data since 06f90a8 (09-24), and an unreadable
  one now returns `sandbox_unavailable` (#322, PR #361, 01f5d0e, 2.15.0). Still
  open, not filed: `flextools_health` sets `sandbox_ready` from HermitCrab and
  GenerateHCConfig.exe only, never checking the script.*
- A filing run ended `stage: failed` with empty notes (C-S9-05, C-S10-02).
  *Fixed: bug #239, a regression from #223/#225 (the filing worker idle-released its
  writable project), filed from this failure and fixed by #240 (98944ef, 09-25,
  2.13.0). The response did carry the reason in `failure` ("'NoneType' object has no
  attribute 'ObjectRepository'", `stage_at_failure: starting`); the 1-2 KB log cut
  hid it. Still open: the failure `next_step` advises `grammar_health` for memory
  exhaustion whatever the stage or error type (T-S9-12; `_failure_rungs` in
  `handlers/parse/summary.py`).*
- Flexicon: `GetAllAffixTemplates` items fail the `IMoInflAffixTemplate` cast
  (T-S6-05); `SetMorph` accepts a wrapper it then rejects (T-S7-04);
  `Allomorphs.GetForm` on a lexeme form fails the `IMoAffixAllomorph` cast
  (T-S9-10); no morph-type name reader (T-S6-05).
  *All fixed in flexicon: #449 (4.10.0) unwraps `GetAll()` wrapper items before the
  cast, which covers the template cast and `SetMorph` (live test
  `test_set_morph_and_set_msa_via_wrapper_repoint_bundle`); related #467, #561
  (4.11.0). `GetForm` dispatches on ClassName since df37e35 (09-07); #599 closed
  as not reproducible. `LexEntry.GetMorphTypeName` (#583, 4.12.0).*
- Flexicon `Wordforms.GetForm("Danieli")` returned `WrapperInternalError` (T-S11-05).
  *Fixed: wrong types raise `FP_ParameterError` (flexicon#600, #618, 4.12.0). The
  MCP-side label is still `WrapperInternalError` for other AttributeErrors (T-63).*
- A write-mode script that raises still commits what it wrote before the raise,
  because the runner's `finally` closes (saves) the project; the error response
  dropped the script's messages, so the 09-30 run looked like a no-op and left 9 bare
  entries (T-S11-10, C-S11-05).
  *Messages fixed (#347, 2.15.0). Commit-on-error is unchanged; read the project back
  after any failed write run (T-08).*

#### P0 -- the loop, locks and concurrency ([Stage 11](stages/11-parse-and-repair-loop.md))

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-67 | **One writer per project**: a cross-session write lease or queue, plus append-merge (not overwrite) on shared Description and text fields | The overnight 09-13 write subagents ran **sequentially**, by the orchestrator's choice, because the MCP holds one global session (D-S7-10; refutes "four subagents in parallel"). Their two `FP_ConflictingSaveError` failures came from the FLEx UI saving underneath, and a second Claude session wrote the same project 01:04-01:31 (C-S7-01, T-S7-03, transcript). The template-description overwrite was the Particle agent's own run, which restored it. A fresh session read the on-disk file, not the shared commit log, and tried to recreate objects (C-S7-13); a concurrent writer likely explains a stale text read at 20:08 (C-S7-12). A second client wrote concurrently on 09-25 (C-S10-06, log only); eight bulk writes ran as a "non-master peer" with FLEx open (C-S8-03, log only) | **Open, not filed.** A conflicting save now fails loudly (`FP_ConflictingSaveError`, flexicon 4.6.0); RefreshFromDisk (#147) and shared-mode work (#93); schema changes are refused while FLEx holds the project (2.15.0). Nothing serializes ordinary data writers |
| T-68 | **The parse loop reachable by every agent.** Parse tools available to subagents; parser calls inside `run_module` redirected to `try_word` / `parse_text` instead of flagged as unprotected writes | The four 09-13 write subagents (00:04-01:31) wrote grammar blind: "cannot be verified without running the parser" (T-S7-01). No AI ran HermitCrab before about 01:57; Matthew closed the loop himself by running the FLEx parser at 01:20 and sending screenshots (D-S7-16). From 01:55 the orchestrator passed the in-process `HCParser` recipe in every brief, and the valency work was parse-verified (V-S7-11). Write and parse cannot share one `run_module` call (`LockRecursionException`, T-S7-04). On 09-30 a nonexistent `Parser.TryWord` was treated as a write, and weaker clients added write guards and retried (T-S11-02) | **Partial.** `Parser.TryWord` in `run_module` is now `unknown_method` with did-you-mean (#306, PR #338, 2.15.0); search routes to the parse tools (#312); user-level `lex-parser`/`lex-linguist` agent definitions carry the parse tools (D-S10-12). The rejection does not name `flextools_try_word` |
| T-69 | **Parse-worker-aware lock handling**: when a write meets `project_locked` held by this server's own idle parse worker, release it (or name it and offer `flextools_parse_release`) | Six `project_locked` rejections right after parse runs (T-S8-04, T-S9-05). `parse_release` did not exist until 09-24 15:41; the agent could not end its own worker (auto mode denied `Stop-Process`, T-S8-12), so Matthew killed workers by hand four times on 09-24 (T-S9-05, transcript). The 09-30 lock holder was FLEx Send/Receive, not a worker (T-S11-08) | **Fixed.** Idle worker drops the lock, `run_module` releases its own worker, and `flextools_parse_release` added (#223 via #225, 3717fb5, 09-24, 2.13.0); `project_locked` names this server's worker with `next_steps` and kills orphaned children (#315, 244e295, 2.15.0) |
| T-71 | **Post-commit verification by reopen** after any teardown warning, reported in the same response | A rule disable read back "True" inside the op and never persisted, "even with an explicit save" (C-S9-02); "writes may not have been committed" was undecidable without a reopen (T-S9-06). Extends T-08 | **Partial.** Stale global writing-system mutex cleared, dispose retried, `writes_committed` reported, TeardownError carries `next_steps` (#302, 7087b32, 2.15.0; missing from CHANGELOG); `effect_check` flags zero-change write runs (#143). No automatic reopen-verify |
| T-73 | **Filing as a human gate with reasons**: a filing confirmation separate from `write_enabled`, scope shown in tokens and analyses at risk, and a failure reason on `stage: failed` | Matthew ordered the 09-25 all-texts filing ("remove *mwaka, file the parses", C-S10-02), but the agent confirmed the plan 21 s after its preview without showing him the 24,259-analysis upper bound (real deletions: 322); the 3.4 MB preview was unreadable anyway (T-S10-11). The 09-25 evening "Filing NOT authorized" was the orchestrating agent's staging prompt, not Matthew's words; he had said "I approve if you do. You're running the show." (D-S10-04, V-S10-10 refuted). The failures did carry a reason; the log cut it (C-S9-05) | **Partial.** Preview + `confirmed=true` + `plan_id`, backup, deletion log; compact preview with the full plan on disk (#252, 2.13.0); the S9/S10 failures were bug #239 (fixed 2.13.0). Open, not filed: an agent can still confirm its own preview |

#### P1 -- diagnosis and lints ([Stages 05, 07, 08](stages/05-categories-and-templates.md))

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-70 | **Morph resolution for restricted `try_word`**: resolve a piece by lexeme, citation or allomorph form, and on `parse_morph_unresolved` return candidate headwords with homograph numbers and morph-type markers | `ake`, `*ake`, `mi`, `mi-`, `roho` all failed with `candidates: []`; the real headwords were `mi-1`, `*aka`, `*roho` (T-S8-02, T-S9-02, T-S10-01). Extends T-02, T-33 | **Open, not filed.** `server/parse/resolver.py` matches the headword only and returns `candidates=[]` on NONE (unchanged since 9cb8af6, 09-20); find headwords with recipe `lexicon-form-lookup` (09-28) |
| T-72 | **Phonological-rule and exception-feature wrappers**: enable/disable a rule or one RHS, set required/excluded features, create rule and exception features, tag entries | Disabling a rule failed through raw casts and never persisted (T-S9-07); an exception feature took four failed raw-LCM attempts (C-S10-05). HermitCrab carries a stem's `ProdRestrict` but treats an affix's `FromProdRestrict` as a requirement, so the exception could not go on the `mi-` prefix (L-S10-07, source reading, untested). Extends T-30, T-61 | **Partial.** `PhonRules.SetDisabled` and stem-MSA `MSA.AddExceptionFeature` in flexicon 4.12.0 (#572, #574); `InflectionFeatures.ExceptionFeatureCreate` and affix-MSA exception features fixed on flexicon main, not yet released (#631, #630); rule features read-only; no per-RHS disable or RHS POS setter |
| T-74 | **Unslotted-inflectional-affix lint** (a `grammar_health` candidate) | An inflectional MSA with no slot is tried in every position; a hand-built audit caught 14 in its own dry run (T-S8-07). The rule is Matthew's mid-turn correction: "unconstrained affixes can apply "anywhere" and create parser slowdowns" (D-S8-08, transcript); all 14 were the agent's own. Sibling of T-49, T-50 | **Open, not filed.** Not in `grammar_health`; recipe `audit-repair-infl-aff-msa-slots` flags duplicate slots only |
| T-75 | **Gloss/feature consistency lint**: a gloss naming N agreement values over an MSA that encodes fewer | `conn.conc.nc4/6/9` carried class 4 only, so the other classes silently failed to unify (L-S8-03, D-S8-07; the one-sense-per-class fix was Matthew's: "For the y affix you may need to add it with multiple senses") | **Open, not filed** |
| T-76 | **Template-reachability lint**: a POS that inherits an obligatory-slot template from an ancestor; template filler MSAs whose POS is neither the template's POS nor an ancestor (inert template) | Pronouns, `amba-` relatives and invariant numerals failed through an ancestor's template; fixing that unblocked about 3,000 tokens (L-S9-01 .. L-S9-03; the diagnosis started from Matthew's "found whole" hypothesis, D-S9-07). An inert Quantifier template (L-S7-04, L-S6-11) | **Open, not filed** |
| T-65 | **`swap_lexeme_with_allomorph(entry, allomorph)`** with a reference-integrity check (morph-bundle references before and after) | Hand-ported from FieldWorks' `SwapAllomorphWithLexeme` and applied to 19 entries (15 swaps, 19 environments cleared, 3,526 bundle references identical before and after); a guessed API (`ReplaceMoForm`, which expects a freshly created form) left an orphan in the work project first (T-S6-03, D-S6-05, D-S6-06, C-S6-01). Sibling of T-31 | **Open, not filed.** No swap wrapper (`BaseOperations.Swap` swaps sequence items) |

#### P2 -- observability and agent guidance

| # | Requirement | Why | Status (2026-10-09) |
|---|---|---|---|
| T-66 | **Per-operation provenance**: an agent/subagent/batch id on every op, and `user_request` refreshed to the latest operator turn (never a subagent prompt or the agent's intent) | Four parallel read-only subagents (09-12) and the sequential write subagents (09-13) logged under one session id and one request (T-S6-07, T-S10-08); the request field froze at the first message or copied the intent (T-S8-06, T-S9-09). Every 09-30 `User request:` line is agent-written (S11 transcript), and mid-turn operator messages never reach the log, so the operator's instructions cannot be recovered from it; several decisions the logs credit to the AI were Matthew's | **Partial.** `user_request` keyed per `session_id`, unknown start args reported as `ignored_params`, `task` aliases `user_request` (#318, d4153e7, 2.15.0); no per-turn refresh, no agent/batch id |
| T-77 | **Repeated-failure circuit breaker**: on the second identical error signature, say so and suggest a different approach or escalation | 14 consecutive identical `'str' object has no attribute 'Form'` failures (16 in 11 minutes), 5 `IStTxtPara`, 6 `unprotected_writes` (C-S11-07, T-S11-09; filed as flexicon#600) | **Partial.** Retry-loop detection existed during S11 (#28, b4d7989, 05-29: 4+ identical error codes in 5 min); `identical_resubmit` on the first repeat (#334) and `closest_recipes` on the second same-intent failure (#335), both cbd2050, 2.15.0. No trigger on a second identical *runtime* error signature |
| T-78 | **Casting checker aware of Flexicon return types**; index `ParseResult` | Advice to cast a Flexicon `ParseResult` to `IStTxtPara` blocked a run and led to five failing retries (T-S11-04, log only) | **Open, not filed.** `ParseResult` appears only in docstrings in `flexicon_api_v4.12.0.json`, so `get_object_api` has nothing; the #316 suppression (5772ed9) fails open on unknown receivers; #308 covers facade calls in comprehensions only |

### Fix status (2026-10-09)

Checked against FlexToolsMCP `main` (cee5a84; latest tag 2.15.0, 2026-10-04) and
flexicon `main` (latest tag 4.12.0, 2026-10-02), with commits and GitHub issues on both
repos. Per-row detail is in the Status column above. Many defects in the S6-S11 logs
were fixed within a day of the event; do not cite them as open.

**Fixed in the MCP (FlexToolsMCP):**
- The parse tools (T-01..T-07, T-32 in part): on main 09-20 .. 09-24, first released in
  **2.13.0** (2026-09-25). The per-analysis breakdown in `parse_log section=results`
  and the CP3 batch signals date from 09-22 (T-01, T-04 partly met all along).
- Lock handling (T-69): the idle worker drops the lock, `run_module` releases its own
  worker, and `flextools_parse_release` exists (#223 via #225, 09-24, 2.13.0);
  `project_locked` names this server's worker with `next_steps` (#315, 2.15.0).
- Filing `stage: failed` was bug #239 (fixed by #240, 2.13.0); large filing previews
  are compact with the full plan on disk (#252, 2.13.0).
- Per-operation units of work in the runner (#144, 2.13.0); a failed run returns its
  messages (#347, 2.15.0) (T-08 in part).
- `DoNotUseForParsing` (a no-op in both parsers) is refused at preflight (a40e250,
  PR #259, 2.13.0); use `IsAbstract` on the lexeme form and every allomorph, recipe
  `hide-entry-from-parser` (T-55).
- Preflight loops (#303, #334, #340, #319, #308, #316; #278 in 2.14.0) and the
  `Parser.TryWord`-as-write misclassification (#306, PR #338) are fixed in 2.15.0
  (T-64, T-68); parse tools surfaced in `search_by_capability` (#312) and recipes put
  in front of the model (#335).
- The teardown AbandonedMutex loop is fixed, with `writes_committed` reported (#302,
  2.15.0) (T-71 in part).
- Per-session `user_request` (#318, 2.15.0) and the UTF-8 child environment (#320,
  2.15.0).
- `parse_sandbox` returns `sandbox_unavailable` instead of crashing on an unreadable
  `hcparse.ps1` (#322, PR #361, 2.15.0).
- Recipes (af8e97d, 09-28, 2.15.0) give recipe-level coverage of T-13
  (`overpowered-allomorphs`), T-48/T-50 (`find-overpowered-affixes`), T-19
  (`form-usage-before-edit`, per entry) and T-23/T-24 (`parser-coverage`).
- Unreleased (after 2.15.0): backup pruning by size and age (#218).

**Fixed in flexicon, released:**
- 4.4.0: per-operation UoW (T-08); `GetPartOfSpeechObject` silent None (#232, T-63).
- 4.6.0: `FP_ConflictingSaveError` raised instead of a silent loss (T-67 in part);
  allomorph stem/affix dispatch (T-37).
- 4.10.0: `POS.CreateAffixSlot`, `MorphRules.AddSlotToTemplate` (T-61); `GetAll()`
  wrapper items accepted back by Operations methods (#449), which fixed the template
  cast (T-S6-05) and `SetMorph` (T-S7-04).
- 4.11.0: slot readers and `AffixSlot` (#542); MorphRule resolver casts every type
  (#561).
- 4.12.0: `PhonRules.SetDisabled` (#572); stem-MSA exception features
  `MSA.Add/Remove/GetExceptionFeatures` (#574); inflection-class, required-feature and
  template-reorder wrappers (#573, #580, #581); rule-feature readers (#572);
  `GetMorphTypeName` (#583); `GetParserCount`/`GetUserCount`/`IsParsed` (#576);
  evaluation wrappers `GetEvaluationsForAgent`/`ClearEvaluation`/
  `RemoveAllHumanEvaluations` (#582); wrong-type arguments raise `FP_ParameterError`
  (#600, #618).
- Already there before the logs: `LexEntry.MergeObject` (2025-12-05; T-54).

**Fixed on flexicon main, not yet released (after 4.12.0):**
- `InflectionFeatures.ExceptionFeatureCreate/Find/GetAll` (flexicon#631).
- Exception features on affix MSAs (`side="from"|"to"`) (flexicon#630). In 4.12.0 the
  #574 wrappers silently do nothing on affixes.
- `InflectionClassCreate(name, pos=...)` (breaking; before this it wrote classes into
  the exception-features list) (flexicon#631).

**Still open:**
- Writing rule features: no wrapper creates a rule feature or sets
  `ReqRuleFeats`/`ExclRuleFeats` on an RHS, and there is no per-RHS disable. Readers
  only (T-72).
- The breakdown in the `try_word`/`parse_text` response itself, slot in the
  breakdown, prose failure explanation, a four-bucket partition and a timing diff
  (T-01, T-02, T-04, T-07).
- A script that raises keeps what it wrote before the raise (runner `finally` closes
  and saves); no session-level transaction (T-08).
- Report output in the operation log (1000-char `[OUT]`; T-43); automatic spill to a
  file (T-42).
- Reopen-verify after commit (T-71).
- `ParseResult` indexing and cast advice (T-78); the coverage, over-generation and
  candidate reports (T-18, T-22, T-23 beyond the recipe); the conversion primitive
  (T-31); the enclitic "attaches to" wrapper (T-39); a grapheme parse-rate check (T-26).
- Custom fields still cannot be created programmatically: flexicon `CreateField`
  refuses by policy, so create them in the FLEx GUI.

**Open with no issue filed (file these):**
- `parse_log` refusing a handle that `available_runs` lists (T-S10-04; probable cause:
  in-memory `known_run_ids` vs the 20-run on-disk retention).
- `flextools_health` reporting the sandbox ready without checking `hcparse.ps1`.
- A failed parse run's `next_step` always gives the memory-exhaustion advice, whatever
  the stage or error (T-S9-12).
- The MCP labels caller AttributeErrors inside flexicon `WrapperInternalError` (T-63).
- Morph resolution with candidates for restricted `try_word` (T-70).
- A cross-session write lease (T-67); a human-only filing gate (T-73: an agent can
  still confirm its own preview).
- The unslotted-affix, gloss/feature, template-reachability lints (T-74, T-75, T-76);
  the swap primitive (T-65).
- The 1000-char `[OUT]` log cut and the 100-message default cap (T-43, T-42).

**Stale notes outside `parsing/` (follow-ups, not fixed here):**
- Recipe `bulk-set-exception-features` notes say flexicon has no exception-feature
  wrapper (#574). `MSA.AddExceptionFeature` is in 4.12.0, and affix MSAs (#630) are on
  main.
- Recipe `phonological-rules` notes say rule contexts, exception features and input
  POS have no flexicon reader (#572). They shipped in 4.12.0.
- The shipped index `flexicon_api_v4.12.0.json` lacks `ExceptionFeatureCreate/Find/GetAll`.
  Refresh it after the next flexicon release.
- Recipe `parser-coverage` defines "parsed" as stored `ParserCount > 0`, the stale
  definition [README 4.16](README.md#416-what-unparsed-means-a-stored-count-s2-s3-vs-a-live-parse)
  warns against. For live coverage, use `flextools_parse_text` and its `NumZeroParses`.
- The FlexToolsMCP `.venv` has pyflexicon **4.11.0**, so none of the 4.12.0 fixes are
  active there until it is upgraded.
- Recipe `ensure-morpheme-entries` (PR #337) was modelled on the 09-30 run that created
  9 bare entries for syllable fragments (T-S11-11). Review it: require POS, gloss and
  morph type, and a linguist check. The local recipe `local-be769c1f63ae` in
  `recipes.jsonl` still stores that junk script; delete it.
- #302 (teardown mutex, `writes_committed`) is missing from CHANGELOG.md.

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
