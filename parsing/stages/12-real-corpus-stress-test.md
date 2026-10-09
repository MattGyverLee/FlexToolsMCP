# Stage 12 -- Real-Corpus Stress Test

[Back to overview](../00-overview.md) | [Prev: Stage 11](11-parse-and-repair-loop.md) | [Next: Stage 13](13-cleanup-and-consolidation.md)

## Purpose

Run the grammar against **real text** rather than constructed paradigms, because
constructed paradigms only test what you already thought of.

> "Create a text of 100 real sentences from the public-domain Aesop fables on
> [Wikisource]." (D-M5-11)

> "delete the Aesop text and normalize and import Matthew chapter 2. Add new
> vocabulary, Create compound rules as needed. add the complementizer enclitic.
> iterate to see how good you can get it." (D-M6-01)

Real text finds three things a paradigm text cannot: missing **lexicon** (words you do
not have), missing **constructions** (compounding, clitics, derivation you had not
modeled), and **frequency-weighted** priorities (what actually matters).

## Entry Criteria

- [Stage 11](11-parse-and-repair-loop.md) converged on the constructed paradigm texts.
  Do not stress-test a grammar that fails its own paradigm -- you cannot distinguish
  the two kinds of failure.

## Inputs

- A **public-domain** real text of meaningful size. The corpus used two: 100 Aesop
  fable sentences from Wikisource, and Matthew chapter 2 from a public-domain
  translation.
- A normalization step producing one unit (verse / sentence) per line.

## Procedure

1. **Choose text that is public domain and reusable.** The corpus's Aesop set is
   explicitly noted as a reusable QC asset (M5 §8). Licensing matters: the grammar
   artifact will carry it.
2. **Normalize before import**, to a one-unit-per-line file in the scratchpad, then
   import as one paragraph per unit with an idempotency guard on the title
   (M6 §5 stage 5).
3. **Import only when the vocabulary plausibly covers the text.** The corpus's entry
   condition is "vocabulary sufficiently covers the target chapter" (M6 §5) -- but see
   step 5: partial coverage is the *point*, total absence of coverage just produces
   noise.
4. **Parse it** ([Stage 11](11-parse-and-repair-loop.md) procedure, same buckets).
   Build the failure list from a **fresh** parse of the whole text (or file parser
   results for all texts first), never from stored analysis counts: on a corpus that
   has been edited since its last parse, a stored-state queue is mostly words that
   already parse (L-S10-01: 14,096 -> 9,260 "unparsed" after one refile, no grammar
   change; V-S11-02). The stored queue measures *unfiled*, not *unparseable*: in each
   09-24 session most of the queue already parsed (5/20, 9/10, 4/5; T-S9-14). Use
   `flextools_parse_text` (all texts) and read its live `NumZeroParses`; the
   `parser-coverage` recipe counts stored `ParserCount > 0` and inherits the
   staleness. Today a reparse of just the zero-count queue takes two calls
   (`parser-coverage`, then `parse_text` on its words; D-S11-06, T-S11-06).
5. **Treat the failure list as the vocabulary work queue.**
   > "Create a Numeral part of speech with a case template, add the Malayalam
   > cardinals, and add the missing lexical items found in the Matthew 2 failures."
   > (D-M8-04)
   Lexical gaps should be **discovered from real-text failures, not guessed**. Round
   after round: the corpus ran "round 1 of new lexicon entries driven by the Aesop
   parse failures" (M5 op 68), then a final reconciliation round (M5 ops 76-77).
6. **Check existing coverage before adding.**
   > "List every third-person pronoun form in the lexicon and check whether [X] is
   > among them." (D-M5-12)
   A parse failure on an unrecognized word may mean the paradigm is incomplete rather
   than that this one word is missing -- check the whole category before adding, to
   avoid near-duplicate entries.
7. **Expect real text to demand new machinery, not just new words.** Matthew 2 forced
   compound rules, the complementizer enclitic, derivational nominalizers, and a whole
   new POS with its template (M6, M8). Route these back to
   [Stage 05](05-categories-and-templates.md) and
   [Stage 09](09-compounding-and-clitics.md).
8. **Reconcile after every bulk round.** Create-if-not-exists silently skips existing
   entries and leaves them without their derived data (D-M5-13). Run the
   "exists but incomplete" pass.
9. **Retire the stress corpus when you move to the next one**, or keep both -- but be
   deliberate. The corpus deleted Aesop when Matthew 2 came in (D-M6-01), losing that
   regression surface.
10. **Regression-check against the constructed paradigm texts** after every round of
    real-corpus-driven changes. New vocabulary and new machinery can break the core
    paradigm (D-M3-01).

## Linguistic Decisions Required

- **Genre and register fit.** The corpus's original pronoun set was
  "honorific/formal-register-heavy and under-covers colloquial third-person forms"
  (L-M5-11) -- a gap only real text exposed. Choosing a text implicitly chooses which
  gaps you will find.
- **Whether a failing token is a word of the language, a proper noun, a typo, or an
  orthographic variant.** Proper nouns in particular need deciding: the corpus gave
  biblical proper nouns dedicated treatment including a scoped phonological rule
  (L-M7-03).
- **Whether to add a word or to fix the analysis.** A failure can mean a missing
  entry *or* that an existing entry's model is wrong.
- **Spelling variants** may need to be added as allomorphs on the same entry
  (L-M8-03).

## QC / Exit Criteria

- The real text parses at or above the agreed threshold.
- Every failure is classified: missing lexicon / missing construction / wrong model /
  not-a-word.
- Every bulk vocabulary round has been reconciled ("exists but incomplete" pass clean).
- The constructed paradigm texts still parse (regression).
- Parse time on the real corpus recorded.
- Any new POS, template, compound rule or clitic introduced by this stage has passed
  its own stage's exit criteria.

## Common Failure Modes

- **Stress-testing too early**, before the paradigm texts converge, so failures cannot
  be attributed.
- **Adding a word that already exists in another form**, because the category was not
  checked first (D-M5-12).
- **"Skip" mistaken for "complete"** on bulk import rounds (D-M5-13).
- **Deleting the previous stress corpus** and losing a regression surface (D-M6-01).
- **Real text dragging in derivation** before the project is ready for it -- the
  corpus's inflection-first scoping (D-M2-01) breaks down here, and this is exactly
  where the derivation-in-an-inflectional-slot mistake was made (C-M6-03).
- **Unicode normalization mismatches** between the imported text and the lexicon
  (D-M8-02) -- normalize the text file, not just the comparison.
- **Info-output truncation** hiding part of a large failure list (M8 §6): pass
  `max_info_messages=0` to `run_module`, or write it to a file. (Swahili: 14,284 rows
  capped to 100, re-run three times, T-S8-05.)
  *Status 2026-10-09: partial -- the cap is flagged in `summary.info_truncated` and
  can be lifted with `max_info_messages=0` (since FlexToolsMCP #25, May 2026); no
  automatic spill to a file (T-42).*
- **A stale or improvised work queue.** A queue from stored analyses ranks words that
  already parse (V-S11-02); an improvised query can sort by object count or alphabet
  instead of occurrences (C-S11-02, C-S11-03).
- **A programme that stops before filing.** The 09-25 top-100 programme fixed 77
  words in Stage 1 (226 of 227 tested words parsed) and deferred filing to Stage 5;
  Stage 2 died and Stages 3-5 never ran, so on 09-30 the top ten "unparsed" words were
  exactly those unfiled fixes (V-S11-04, L-S10-08). File each batch, or close the
  programme, before building the next queue.

## Automation Notes

**Automatable now:** normalization, import with idempotency guard, parse-failure
enumeration, candidate-list construction from failures, existence checks with
normalization, and bulk creation rounds.

**Human required for:** genre choice, and classifying failures as word / proper noun /
typo / model error.

**Now available** (FlexToolsMCP parse tools, used in S8-S11): corpus-scope
`parse_text` (all texts, 26,725 words) with two-step filing; top-N verification by
`try_word`; `parse_diff` for a regression set; `grammar_health` for parse-cost
warnings. A corpus-wide run is slow (about 3.2 s/word measured on the Swahili
grammar, so about 95 minutes for 1,783 words; D-S10-05), so it is its own step,
never started unasked inside a repair loop. On 09-24 an agent issued an all-texts
parse; Matthew rejected the call within a minute and restated "(don't run the parse
yet)", then again at 15:02 (D-S9-13, D-S9-02; C-S9-01 corrected by transcript). The
aborted run's worker kept the old lexicon and made the next verification parse
stale. Long runs also die with the server: both 09-25 Stage 2 baselines stopped at
word 173 when the MCP server restarted (D-S10-05).
*Status 2026-10-09: these tools first shipped in FlexToolsMCP 2.13.0 (2026-09-25);
S8-S11 used them from a pre-2.13.0 main checkout (the logs say 2.12.0).*

**Missing tooling (requirements):**
- **`failures_to_candidates(parse_run)`** -- turn a parse run's zero-analysis tokens
  directly into a deduplicated, normalized candidate list with a per-token guess at
  category, ready for review. The corpus built this by hand each round. *Still
  missing on 09-30:* the frequency queue was hand-rolled four times in one day, and
  only one version was right (T-S11-06).
  *Status 2026-10-09: partial (T-23). Recipe `parser-coverage` ("most frequent
  unparsed wordforms", af8e97d, 09-28) existed on 09-30 but was not surfaced to models
  until #335 (cbd2050, 10-02, 2.15.0), so the 09-30 client never found it.
  `parse_text` orders its scope by occurrence, which gives a fresh frequency queue,
  but nothing builds candidates from a parse run.*
- **Coverage statistics per run**: token coverage, type coverage, and the frequency
  distribution of failures -- so the work queue is frequency-ordered rather than
  arbitrary. *Still missing, and needs one definition:* three definitions of
  "unparsed" gave 14,096, 9,066 and 0 on the same day (T-S10-09); on 09-24 the count
  read 14,038, 14,006, 13,927 (in texts) and then 14,105 (all 27,708 wordforms) as
  the definition changed, not the grammar (T-S9-11); the 09-20 module's three
  variants gave 14,482, 14,371 and 14,283 (D-S8-13).
  *Status 2026-10-09: partial (T-24) -- `flextools_parse_text` run summaries carry live
  type-level counters (`NumWords`, `NumZeroParses`, `TotalAnalyses`), and
  `search_by_capability` routes "unparsed"/"coverage" to it (#312). `parser-coverage`
  fixes one stored definition (occurs in texts, `ParserCount > 0`, frequency from
  `GetOccurrenceCount`), and flexicon 4.12.0 adds `GetParserCount`/`GetUserCount`/
  `IsParsed` (#576); both still read stored state. No token-weighted coverage figure
  and no per-run statistics.*
- **Parse rate per grapheme** -- a cheap orthography check: graphemes whose words
  parse far below the corpus mean are coding defects (D-S10-06; T-26).
  *Status 2026-10-09: open -- nothing in either repo.*
- **`category_coverage(pos)`** -- is this paradigm complete, before adding one more
  member to it (D-M5-12)?
  *Status 2026-10-09: unverified -- not tracked in the status ledgers.*
- Text normalization and import as a single call, with the normalization rules
  recorded alongside the text.
  *Status 2026-10-09: unverified -- not tracked in the status ledgers; the nearest
  piece is recipe `create-text-from-lines` (FlexToolsMCP #138).*
- Keeping multiple stress corpora simultaneously with per-corpus parse reporting, so
  retiring one is not necessary (D-M6-01).
  *Status 2026-10-09: unverified -- not tracked in the status ledgers.*

## Second-Operator Evidence (Swahili)

*Matthew's Swahili practice (project Claude-Swahili), from shards S1-S11 in the [evidence index](../evidence/directive-index.md); S1-S5 and S6-S11 are the logs of two machines and together cover the project. Labels: **CONFIRMS** / **ADDS** / **CONTRADICTS** Ron's practice above; **REVISES** marks an S6-S11 finding that corrects an earlier S1-S5 claim. Sessions run by other clients are cited only as failure-mode evidence.*

- **CONFIRMS a frequency-ordered work queue** (D-S3-02, D-S2-06): "List top wordforms
  with 0 analyses, sorted by occurrence count desc". It ran as an eight-round loop over
  Genesis.
- **ADDS a failure mode: a queue without an entry standard produces listing, not
  analysis** (C-S3-01). Possessives, inflected verbs and prefixed nouns went in as stems
  (`zake`, `msifuni`, `mnyama`). The August parse-ready standard (D-S3-03) cleaned this
  up afterwards. A heuristic affix stripper with hard-coded affix lists was rewritten
  about eight times. Read the affixes from the slots instead (T-23).
- **ADDS: a path with no text at all** (D-S3-06). *"only phase 0 from lexical resources,
  no digging into texts and wordforms"*: population driven by outside lexical sources
  (Stage 06's licence policy, D-S3-05) rather than by corpus failures.
- **EXTENDS step 1 (licensing)** to lexical sources as well as texts (D-S3-05).

*S6-S11 (this machine, 2026-09-12 .. 09-30):*

- **CONTRADICTS the entry criterion, in practice** (V-S9-08, V-S7-04). The whole
  S9-S11 repair loop ran on the Bible corpus (Musa, Waisraeli, Torati) with no paradigm text in use, although paradigm texts for every template
  had been built on 09-13. Real text came first and stayed the driver; see
  [README 4.12](../README.md).
- **REVISES the S1-S5 frequency queue** (D-S3-02, D-S2-06 -> L-S8-01, L-S10-01,
  V-S11-02, T-S9-14). The queue Matthew asks for ("find 20 of the wordforms with the
  most occurences and 0 parser analyses", D-S8-13; D-S9-01, D-S10-01; the 09-30
  wording, D-S11-02, is the client's paraphrase) is right, but built from stored
  evaluations it is stale and measures unfiled words; S1-S5 "unparsed" figures should
  be read as "not parsed since the last FLEx parse". Refile, or parse the top N,
  before triage (procedure step 4). Matthew asked for that targeted reparse himself
  on 09-23 and again on 10-02 (D-S8-18, D-S11-06). On 09-24 he scoped it "(don't run
  the parse yet) ... individually" (D-S9-01, 14:41).
- **ADDS a queue definition** (D-S11-02, T-S10-09): token occurrences
  (`GetOccurrenceCount`), descending; exclude punctuation and numerals; "unparsed" =
  occurring with no parser-evaluated analysis from a current run.
  *Status 2026-10-09: partial -- `parse_text` gives live counts in occurrence order;
  the `parser-coverage` recipe (09-28) fixes the stored definition but still reads
  stored `ParserCount`, so it stays stale.*
- **ADDS: work the head of the queue by kind** (L-S8-02, L-S9-01 .. L-S9-03,
  D-S10-03). On a real corpus the head is proper names (Isa 1,141 tokens), vocatives,
  pronouns and function words, and free words blocked by an inherited template --
  not morphology. One stem or one POS fix clears thousands of tokens. On 09-25
  Matthew asked for "/lex-linguist and /lex-parse teams" working the top 100 "in
  batches" (D-S10-03), approved all 11 grammar options offered (D-S10-16), and said
  "I approve if you do. You're running the show." The orchestrating agent split the
  work into read-only diagnostic batches by kind (names/loans/interjections; function
  words; zero-prefix nouns and orthography; verbs), then lexicon-only writes (Stage
  1), then grammar-wide changes as a separate Stage 2, with filing deferred to Stage
  5 by its own choice (D-S10-04). Only Stage 1 ran (L-S10-08); see the failure mode
  "a programme that stops before filing" above.
- **ADDS two ways to decide a new word's model from the corpus** (D-S10-07,
  D-S10-08): copy POS, features and inflection class from a *parsing* comparator of
  the same kind (Musa for names, safi for adjectives), and infer a noun's class from
  the agreement on the following word (*mamlaka ya*, *hukumu zake* -> 9/10).
- **ADDS a grapheme parse-rate check** (D-S10-06). Overall 66% parsed, but words with
  gh 7%, th 17%: the apostrophe of ng' was coded U+0027 while the text uses U+02BC
  (also L-S8-05). Route to [Stage 02](02-phoneme-inventory.md).
  *Status 2026-10-09: the L-S8-05 default-codepage crash on U+02BC is fixed in
  FlexToolsMCP 2.15.0 (#320, scripts run in UTF-8 mode); the data-coding mismatch is a
  project fix, not a tool fix.*
- **CONFIRMS step 10, with a corpus baseline in place of paradigm texts** (D-S10-05):
  the top 1,500 frequent *parsed* words plus words containing the targeted segments,
  1,783 in all -- about 95 minutes at 3.2 s/word. It never completed: both attempts
  died at word 173 when the MCP server restarted, and the agent stopped before running
  it in chunks. Size the baseline to parse time, and chunk it.
- **CONFIRMS "real text dragging in derivation"** (C-S10-03, C-S7-06). To make
  *akamzaa* and *mzaliwa* parse, applicative and passive stems (zalia, zaliwa) were
  stored first as allomorphs, then as separate entries -- after the extensions had
  been made derivational. The split went in as a "lexicon-only" fix and was never put
  to Matthew (his approval covered only the `a-`/`n` question), and the agents' own
  linguist brief segments *zalia* as za-li-a. A quick fix against P10 (Q-40).
- **ADDS: build the grammar, not whole words** (D-S10-15, C-S10-09). Matthew: "you
  said "I recommend whole-word entries (yuko, yupo, yumo) for now ..." but I do want
  you to build it properly." Twelve minutes later the AI narrowed his explicit
  approval of derivational -aji/-o/-i back to whole-word entries for -o and -i. Report
  a deviation from an approval; do not narrow it silently.
- **ADDS a "word or analysis" failure mode** (C-S11-04, C-S11-05, C-S11-08, C-S8-04).
  Agents without a linguistic segmentation called words "monomorphemic" because they
  failed to parse, regex-stripped affixes, or created entries for syllable fragments.
  On 09-30 the fragments came from a decomposition table the client invented, and 9
  of them were committed as bare entries (malaka, el, kumu, gizo, is, hara, en,
  ghadha, bu). A new stem needs a segmentation a linguist would accept, a sense, a
  gloss and a POS.

## Provenance

- M5 ops 62, 68, 72, 76-78 (2026-09-14 12:37 .. 14:21); **D-M5-11, D-M5-12, D-M5-13**;
  L-M5-11; M5 §8 (Aesop as a reusable QC asset).
- M6 ops 1, 4, 26 and throughout (2026-09-14 16:01-16:45); **D-M6-01**; M6 §5 stage 5;
  C-M6-03.
- M8 ops 1-6 (2026-09-15 14:02-14:09); **D-M8-01, D-M8-04**; L-M8-02, L-M8-03;
  D-M8-02.
- M7 L-M7-03 (proper-noun-specific rule scoping arising from the biblical text).
- S6-S11 (Swahili, this machine, 2026-09-20 .. 09-30): L-S8-01, L-S8-02, T-S8-05,
  D-S8-13, D-S8-18; D-S9-01, D-S9-02, D-S9-13, C-S9-01, V-S9-08, T-S9-11,
  **T-S9-14**; **L-S10-01**, D-S10-03, D-S10-04, D-S10-05 .. D-S10-08, D-S10-15,
  D-S10-16, C-S10-03, C-S10-09, L-S10-08, T-S10-09; **D-S11-02**, D-S11-06,
  C-S11-02 .. C-S11-05, C-S11-08, T-S11-06, V-S11-02, **V-S11-04**. Corrected against
  the Claude Code transcripts and FlexToolsMCP / flexicon fix status on 2026-10-09.
- **Merge seam:** Merged with S1-S11 (both machines) -- see Second-Operator Evidence above. Matthew frequency-orders the queue over Bible text; the queue must come from a fresh parse.
  *(Original seam: Matthew's corpus sources and licensing practice; whether he frequency-orders the work queue.)*

## Open Questions

- No coverage threshold was ever set for a real corpus. Q-23.
- Whether deleting the Aesop text (D-M6-01) cost a regression surface that was later
  missed is not recorded. Q-26.
- Whether the Matthew 2 parse ever converged is not visible in the corpus; M8 ends
  mid-repair. Q-24.
