# Contract: the run artifact

**Date**: 2026-09-22 · **Spec**: [`../spec.md`](../spec.md) · **Data model**: [`../data-model.md`](../data-model.md)

Phase 1 output. **This is a forward commitment.** CP4 and CP5 both read this
artifact without reopening the FieldWorks project, so a shape chosen loosely
here is migrated twice later. It is frozen at the end of the plan's Phase 2,
before anything that consumes it is written.

> **FROZEN -- 2026-09-22, at T053.** Reconciled line by line against the
> shipped `server/parse/record.py`, `runner.py` and `worker_main.py`. From
> here, changes are **additive only** (section 9). Three places where the
> shipped shape differs from the Phase 1 draft are called out inline as
> *Reconciled*; each is a deliberate implementation decision recorded in
> `.spec-context.json`, not drift:
>
> 1. **Identifiers are GUID strings, not integers** -- in the analysis
>    signature (section 4) and in the fingerprint's `text_ids` (section 3).
>    An hvo is a session-scoped handle that liblcm renumbers on every cache
>    load (issue #103); a durable artifact keyed on hvos would misreport
>    every word as `changed`, and refuse every comparison, after any worker
>    restart.
> 2. **`results.jsonl` keeps CP2b's line shape** and carries the batch fields
>    inside `parse` (section 4), rather than flattening them to the draft's
>    top-level keys. One line shape for every run; additive for CP2b readers.
> 3. **`load_error_baseline` is an object, not a bare list** (section 3), so
>    it can say *that* it was not captured, and why, instead of recording
>    zero errors.

---

## 1. Layout

CP2b's layout, **as shipped** (`server/parse/record.py:34-42`), plus exactly
one net-new file:

```text
<record dir>/<run_id>/
├── meta.json        # the durable run record -- REWRITTEN whole on stage change
├── results.jsonl    # one line per completed word -- APPENDED and flushed
├── words.txt        # the resolved word list -- NET-NEW at CP3
├── traces/<n>.xml   # trace payloads, out of line, only where a drill-down was taken
└── filing/deletions.jsonl  # CP4, filing runs only: pre-deletion captures (section 10)
```

`<record dir>` is `record.get_record_dir()`, overridable by
`FLEXTOOLSMCP_PARSE_RECORD_DIR`.

### Why this and not the parent spec's listing

The parent spec's section 5.5 names `run.json`, a flat `trace.txt` and four
sandbox files. **That listing is the thing that is wrong** (D-6): it was
written before CP2b existed and describes a layout no code has ever matched.
CP2b shipped `record.py` at `e5afbfd` with these names, and that code is what
CP3 is required to consume without adding a second execution model.

Renaming shipped files at CP3 would be churn on an artifact CP4 and CP5 both
read, to satisfy a listing nothing ever wrote. **CP3 corrects the parent spec
instead**, and that correction lands with CP3 rather than being left as a
silent divergence -- otherwise the next reader comparing the spec to the disk
concludes the implementation drifted, when the opposite happened.

Out-of-line traces are also better on their own merits: a trace payload is XML
measured in tens or hundreds of kilobytes, and a flat `trace.txt` would force
every run to carry every trace in one file.

---

## 2. `run_id`

**32 lowercase hex characters**, minted by `record.new_run_id()`
(`secrets.token_hex(16)`), validated by `\A[0-9a-f]{32}\Z` on every path
construction.

- **Carries no timestamp.** The source document specified a
  timestamp-plus-suffix form; CP2b mints random hex. FR-022 keeps the shipped
  form, and it is **not** re-minted at CP3.
- **Server-issued, always.** It is a path component. A caller-supplied string
  would make directory traversal reachable from a tool argument.

---

## 3. `meta.json`

Rewritten whole on every stage change, via temp file then `os.replace` --
atomic on both POSIX and Windows, so a status poll landing mid-write reads one
whole state or the other, never a half-written file.

**CP2b fields** (unchanged): `run_id`, `stage`, `project_name`, `words_total`,
`words_completed`, `created_at`, `updated_at`, `interleaved_by`, `failure`,
`stage_at_cancel`.

**CP3 additions**: `scope_fingerprint`, `engine_at_submission`,
`engine_changed_midjob`, `load_error_baseline`, `counters`,
`counter_divergences`, `words_path`, `project_state`.

**CP4 additions** (additive, parser-check CP4): `filing`.

**CP5 additions** (additive, parser-check CP5): `spine`, `sandbox`.

Field meanings are in [`../data-model.md`](../data-model.md) sections 3 and 4.
As shipped (`record.RunMeta`):

| Field | Shape | Present on |
|---|---|---|
| `scope_fingerprint` | the eight-field object of data-model section 3; `text_ids` are text **GUID strings**, sorted (*Reconciled*, item 1) | batch runs; `null` on a single-word run |
| `engine_at_submission` | string, e.g. `"HC"` -- the engine that passed the gate at submission | batch runs |
| `engine_changed_midjob` | bool; `true` is a **warning**, never a refusal (FR-024) | always (`false` by default) |
| `load_error_baseline` | `{"captured": bool, "source": str, "errors": [{"type": str, ...}], "reason"?: str, "scope_fingerprint_key": str}` (*Reconciled*, item 3). `errors` are the HermitCrab loader's `<LoadError>` entries with their child elements, **`Hvo` children dropped** (session-scoped). `scope_fingerprint_key` is `fingerprint.fingerprint_key(scope_fingerprint)`: the baseline sits **beside** the fingerprint, keyed to it, never inside it (FR-023, D-3) | batch runs, once the first word is parsed |
| `counters` | object of exactly the eight host names (section 4 of `contracts/tools.md`) -> int | batch runs |
| `counter_divergences` | list of two strings, each beginning `"<CounterName>:"` | batch runs |
| `words_path` | `"words.txt"` | batch runs; `null` otherwise |
| `project_state` | `ProjectParseState.to_dict()` from the ONE probe (`parse/project_state.py`, FR-004), read at submission: `parser_has_ever_run`, `analyses_total`, `parser_created_analyses`, `human_opinion_analyses`, `indeterminate_analyses`, `truncated`. The oracle's precondition (FR-041). *Added additively after the freeze, at US5 (section 9, rule 1).* | batch runs; `null` if the probe could not run |
| `filing` | the filing section of CP4's data-model section 7: `requested`, `confirmed_plan`, `plan_id`, `backup`, `no_recovery_warning`, `send_receive`, `access_verdict`, `state` (`filing` \| `completed` \| `cancelled` \| `refused_midrun` \| `crashed` \| `failed`), `counts`, `projected_deletions`, `actual_deletions`, `in_use_approvals_recorded`, `disapprovals_overwritten`, `filed_words`, `divergences`. *Added additively at CP4 (parser-check-cp4/data-model.md section 7); a CP3 reader never sees it on a read-only run.* | filing runs (`apply=true`) only; `null` on every read-only run |

**Written incrementally** (FR-016), not only at completion: progress and
counters are rewritten after **every** word, not only on a stage change. A run
that dies during grammar loading and never reaches a first word still states its
terminal state and the stage it died in, and a run killed at word four thousand
says `words_completed: 4000`.

**Terminal failure** carries exactly one of `out_of_memory | crashed |
cancelled`.

**An engine change mid-job is a warning on the summary, not a refusal**
(FR-024). The engine recorded at submission is the one the results are labelled
with.

---

## 4. `results.jsonl`

One JSON object per line. **Appended, flushed and `fsync`ed before the call
returns** -- already true of `record.append_result`.

The flush is the requirement, not an optimization: a buffered write loses the
tail of a killed run, and the tail is exactly what matters, since a run is
usually killed because of what it was doing at the end.

**Readers must tolerate a malformed trailing line.** A run killed mid-write can
leave a partial final line; everything before it stays valid.
`record.iter_results` already skips rather than raises, and **CP4 and CP5
readers must do the same.** Raising would throw away the results the record
exists to preserve.

Line shape, as shipped (*Reconciled*, item 2) -- CP2b's line, with a batch
run's structured result inside `parse`:

```json
{
  "index": 0,
  "wordform": "membuat",
  "parse": {
    "parsed": true,
    "analysis_count": 1,
    "analyses": [
      {
        "signature": [["<form guid>", "<msa guid>", null]],
        "rendered_morphs": ["mem", "buat"],
        "category_labels": ["v", "v"],
        "has_guessed_form": false
      }
    ],
    "human_analyses": [
      {
        "analysis_guid": "<guid>",
        "opinion": "approves | disapproves | noopinion | unreadable",
        "bundle_count": 2,
        "complete_bundle_count": 2,
        "signature": [["<form guid>", "<msa guid>", null]],
        "rendered_morphs": ["mem", "buat"]
      }
    ],
    "error_message": null,
    "parse_time_ms": 12
  },
  "trace_path": "traces/0.xml"
}
```

- `signature` is the ordered (morph-form, morph-syntax-analysis,
  inflection-type) triples, each a **lowercase GUID string** or `null` for an
  absent reference (*Reconciled*, item 1). Read from the parser's typed
  structured result, never its document form (FR-035).
- `has_guessed_form` is per analysis (FR-031a).
- `human_analyses` are the wordform's stored analyses, read beside the parse.
  `opinion` is the **human** opinion only. `bundle_count` and
  `complete_bundle_count` (bundles whose public `IsComplete` is true) are the
  raw facts the completeness tier is derived from (FR-038); the tier itself is
  not stored.
- *Added additively after the freeze, at US5 (section 9, rule 1).* Each
  `analyses[i]` also carries `entry_guids` (the owning entry of each morph's
  form, lowercase GUID or `null`), `morph_kinds` (`"stem" | "affix" |
  "unknown"` per morph, from the morph type's public flags) and
  `morph_glosses` (the gloss of the sense carrying each morph's MSA, at the
  default analysis writing system; `""` where none). Each `human_analyses[i]`
  also carries `gloss` (the first word gloss), `category_label`,
  `parser_evaluated` (bool), `evaluator` and `evaluated_at` (the first human
  evaluation's agent name and date, `null` where unreadable), and
  `in_segment` (`true | false | null` -- `null` when the segment-occurrence
  join could not be built; never collapsed to `false`). These are what the
  batch signals, the oracle and the projections read (`server/signals/`).
  A run recorded before them reports the dependent signals as not
  computable.
- `trace_path` is present only where a drill-down wrote a trace.
- A word that failed without ending the run carries `"parse": null` and
  `"error": {"message": str, "error_type": str}` instead.
- A single-word (CP2b) run's `parse` carries only its level's keys
  (`parsed`/`analysis_count`, `hypothesis_held`/..., or `parse_error`) -- no
  `analyses`. Readers must not assume `analyses` exists.

---

## 5. `words.txt`

The resolved word list. UTF-8, NFC, one word per line, in resolved order
(descending occurrence, then alphabetical, truncated after ordering). Every
line, including the last, ends in `\n`; no BOM. Written once, at run creation,
**before** the first `meta.json`, so a meta that names it always has it. Absent
(never empty) on a single-word run.

**The only genuinely net-new file at CP3.** The source document also calls
`results.jsonl` net-new; it is not -- it shipped with CP2b. The word list is
the one thing with no persistence today.

---

## 6. `traces/<n>.xml`

Out-of-line trace payloads. `<n>` is an **int supplied by the runner**, never a
caller string, so the filename cannot carry traversal.

Written **only where a drill-down was taken** (FR-047: capped at a user-chosen
10-20 per session, never auto-traced in bulk). A completed batch over ten
thousand words normally has an empty or absent `traces/` directory.

---

## 7. What is NOT written

**Sandbox-spine files are not written, and are not created empty** (FR-015).
That is CP5's spine. `flextools_parse_log` returns a typed
not-applicable-for-this-spine response naming the spine and the checkpoint that
will fill it -- never an empty section, which reads as "nothing happened."

**No live data-model object reference is ever serialized** (FR-021). The
durable signature and enough rendered text to report without reopening the
project are serialized instead; live references are kept only within the run.

**Nothing here is written to the FieldWorks project.** The artifact is
server-side only (FR-063).

---

## 8. Retention

**Newest 20 runs per project**, ordered by **recorded creation time** --
`meta.json`'s `created_at` (FR-022).

Two mechanisms are explicitly rejected:

- **Not a lexicographic sort of directory names.** The existing backup pruner
  (`server/backup.py:50`) sorts names, and its own comment records that this is
  chronological *only because* backup directories are timestamp-named. Run
  directories are opaque hex, so the same sort would prune in effectively
  random order. FR-022 adopts the pruner's **policy** and rejects its
  **mechanism**.
- **Not `record.list_run_ids()`'s `st_mtime` order.** That ordering is correct
  for its own caller (naming the handles that exist), but mtime is bumped by
  later activity such as a drill-down trace landing in `traces/`, so it is not
  creation order.

A retention implementation that sorts names fails its test.

---

## 9. Compatibility rules for CP4 and CP5

Stated here because this is the file those checkpoints will read.

1. **Additive fields only.** A reader must ignore unknown keys in `meta.json`
   and in a `results.jsonl` line.
2. **Tolerate a truncated final line** in `results.jsonl`, always.
3. **`run_id` form is fixed** -- 32 hex, no timestamp. Do not derive ordering
   from it.
4. **Do not rebuild the segment-occurrence join.** It is built once at CP3 and
   structured for reuse; CP4's deletion projection is the same join for the
   opposite purpose, and a CP4 that rebuilds it is a review finding (FR-043).
5. **Do not grow a second project-state probe.** CP3's is built once with three
   named consumers, and CP4's deletion-projection precondition is the third
   (FR-004).
6. **`traces/` may be absent.** An empty drill-down history is the normal case.

---

## 10. CP4 additions (additive; parser-check CP4)

Everything above is unchanged. CP4 adds three things, and removes nothing:

1. **`load_error_baseline.eligible_entries`** -- on every BATCH run's baseline,
   once the grammar is loaded: `[{"entry_guid": str, "headword": str}]`, the
   entries whose forms could reach that grammar (CP4 FR-039, D-1). A read-only
   run therefore re-baselines BOTH halves of CP4's refuse-to-file gate: its load
   errors, and its eligible forms. A baseline written before CP4 has no such key;
   the gate then compares load errors only and says so. (Recorded with headwords,
   not bare GUIDs, so a dropped entry can be named even after it was deleted.)
   A single-word run never pays for the lexicon walk and records none.
2. **`meta.json` `filing`** -- the filing section (CP4 data-model section 7; the
   row in section 3 above). Present only on a run created with `apply=true`;
   `null` on every read-only run. A filing run is NEVER used as a gate baseline:
   only a read-only run re-baselines (CP4 FR-021).
3. **`filing/deletions.jsonl`** -- filing runs only. One JSON line per analysis
   filing may delete (`kind: "pre_deletion"`) or whose human disapproval it
   overwrites (`kind: "disapproval_overwrite"`, with `prior_user_opinion`),
   written and fsynced BEFORE the filer runs: `wordform`, `analysis_guid`,
   `morph_bundles` (`morph_guid`, `msa_guid`, `infl_type_guid`, `form`),
   `glosses` (`guid`, `form_by_ws`), `evaluations` (`agent_guid`, `agent_name`,
   `human`, `opinion`, `date`), `category`. What then happened is a SECOND line
   per analysis, never a rewrite (the file is append-only): `confirmed_after` is
   `deleted` / `survived` for a capture, `overwritten` / `unchanged` for an
   overwrite. Served by `flextools_parse_log(section="deletions")`; a read-only
   run answers that section with a typed not-applicable.

Rule 1 of section 9 covers all three: a reader that ignores unknown keys reads a
CP4 record exactly as it read a CP3 one. And, as ever, nothing here is written
inside a FieldWorks project folder (CP4 FR-042): the whole record lives under
`record.get_record_dir()`, and a record directory inside the projects directory
is refused at filing time.

---

## 11. CP5 additions (additive; parser-check CP5)

Everything above is unchanged. CP5 adds a second spine -- the sandbox, which
runs the stand-alone `hc` against a configuration exported from a copy of the
project -- and records its runs in this same artifact. It adds two `meta.json`
fields, one run subdirectory, and additive keys on the `results.jsonl` line. It
removes nothing. Field meanings are in
[`../../parser-check-cp5/data-model.md`](../../parser-check-cp5/data-model.md)
section 6.

1. **`meta.json` `spine`** -- `"in_process" | "sandbox" | null`
   (`record.SPINE_IN_PROCESS`, `record.SPINE_SANDBOX`). Default `null`, and
   `null` is **read as `"in_process"`**, so every pre-CP5 record reads
   correctly (CP5 FR-037). Readers branch on `RunMeta.effective_spine`, never on
   the raw value. `flextools_parse_log` decides which sections apply from it.
2. **`meta.json` `sandbox`** -- the sandbox section (CP5 data-model 6.2).
   Present only on a sandbox run; `null` on every in-process run. As written by
   `sandbox/client.py`:

   | Key | Shape |
   |---|---|
   | `mode` | `"parse" \| "test"` |
   | `config_source` | exactly one of `{"kind": "project_cache", "cache_key": str}` or `{"kind": "named_sandbox", "name": str, "edited": bool, "predates_project_grammar": bool}` |
   | `corpus` | `{"name": str, "assertion_count": int}`; `mode == "test"` only |
   | `versions` | `{"hc_tool", "fieldworks_hermitcrab", "generate_hc_config", "hcparse"}`, each str \| null -- read from file metadata, never compared to a floor (FR-005) |
   | `version_skew` | bool, recomputed from `versions` on every update; `true` adds the `hc_engine_version_skew` advisory. A warning, never a refusal |
   | `hc_source` | `"override" \| "path" \| "dotnet_tools_dir" \| "dotnet_tool_list"` |
   | `generation` | `{"reused_cache": bool, "cache_key": str, "load_error_count": int, "load_errors": [...]}`; `null` until the config is resolved |
   | `copy` | `{"bytes": int, "cleanup": "deleted" \| "failed" \| "not_made", "path_if_failed": str \| null}` |
   | `hc` | the run outcome folded from the script's `run.json` (FR-023): `exit_code`, `timed_out`, `killed`, `in_flight_index`, `in_flight_word`, `duration_ms`, `counters` (`"ok" \| "unavailable_timeout" \| "unavailable"`), `hc_counters`, `stdout_bom`, `script_exit_code`, `watchdog_fired`, `load_error` (hc's `Load Error:` line, or `null`) |
   | `truncated_by_limit` | bool |
   | `advisories` | list of code strings (`sandbox_predates_project_grammar`, `hc_engine_version_skew`, `grammar_load_errors`), a union -- a code is never removed once added |

   Updates **merge**: nested objects merge key by key, `advisories` is a union,
   and anything else is replaced. On a sandbox run the existing fields are also
   filled: `scope_fingerprint` with `scope_kind: "words"`, `engine: "HC"` and
   `vernacular_ws: ""` (the vernacular writing system is not known without
   opening the project); `project_state.staleness` on the shared-mode verdicts
   (R-13); and `counters` / `counter_divergences` from hc's `stats -p` or
   `stats -t` line.
3. **`<run_id>/sandbox/`** -- the sandbox run's own files, a closed set
   (`record.SANDBOX_FILES`); `RunRecord.sandbox_path` refuses any other name,
   and every path goes through `_child` (no absolute path, no `..`). The
   directory is created on first write, never up front: **an in-process run
   has no `sandbox/` at all**, so section 7's first paragraph still holds for
   it.

   | File | Written by | Encoding and content |
   |---|---|---|
   | `generate-config.log` | the client | UTF-8. The generator's stdout and stderr verbatim (copied from the cache entry). On a warm run it is prefixed by one line naming the reused entry; on a named-sandbox run, by one line saying no generation ran |
   | `hc-script.txt` | the script | UTF-8, **no BOM**. One command per sent word, then `stats -p` (parse) or `stats -t` (test). Never `tracing on`, `-o` or `-c` |
   | `dispatch.json` | the script, before hc starts | UTF-8. Per-word `{index, word, sent, line, reason, flags}` |
   | `hc-stdout.txt` | the script | UTF-8, no BOM, **decoded from hc's UTF-16LE** stdout (a BOM is stripped and recorded as `hc.stdout_bom`), flushed per line so a killed run keeps every line it printed |
   | `hc-stderr.txt` | the script | UTF-8 |
   | `hc-output.txt` | the client | UTF-8. `hc-stdout.txt` minus the load banner |
   | `run.json` | the script, in `finally` | UTF-8. The hand-off Python folds into `meta.sandbox`; console prose is never scraped |

   `flextools_parse_log` serves them as `config_generation`
   (`generate-config.log`, plus the itemised load errors), `hc_stdout` and
   `hc_output`. An empty file is reported as empty, never as a missing section.
4. **`results.jsonl`, the sandbox line** (CP5 data-model 6.4;
   `classify.word_result_to_line`). CP3's line with additive keys inside
   `parse`, in this order: `parsed`, `analysis_count`, `outcome`, `analyses`,
   `position`, `flags`, `parse_time_ms`. `wordform` is the word **as sent**.
   - `outcome` is a closed enum (FR-018): `parsed`, `not_parsed`,
     `invalid_segment` (with `position` set), `not_expressible` (never sent),
     `error_no_output` (the word in flight at a crash or timeout),
     `not_reached` (never processed because of a timeout, crash or cancel).
     `parsed` is true only for `parsed`.
   - `analyses` is a list **only for `parsed` and `not_parsed`**. For every
     other outcome it is `null`, with `analysis_count: 0` -- CP3's
     `HostCounters` reads `analyses: []` as a zero-parse word, which a word hc
     produced nothing for is not.
   - Each analysis is `{signature, rendered_morphs, morphs, readable, raw}`.
     `signature` is always `null` (hc has no LCM identifiers).
     `morphs` is `[{"form", "gloss"}]`, read from hc's `Morphs:` / `Gloss:`
     columns. An empty gloss is `"?"`: real hc substitutes it (`MorphInfo.cs:25-26`,
     CP5 research F-6) and `MorphInfo.Equals` compares the substituted gloss
     (F-7), so a seeded expectation `form:?` round-trips exactly.
     An analysis that could not be read has `readable: false`, keeps
     hc's raw lines in `raw`, and has `morphs` and `rendered_morphs` `null`
     (FR-019). `raw` is otherwise `null`.
   - `flags` is a list of strings, e.g. `leading_dash_unverified` (R-09).
   - `parse_time_ms` is hc's `Parse time: <n>ms` when it printed one, else
     `null` (none for an invalid segment).
   - A sandbox line carries no `human_analyses` and no `trace_path`: CP5 has no
     trace and never reads the project's stored analyses.
5. **`results.jsonl`, the assertion line** (test mode; CP5 data-model 6.5;
   `classify.assertion_to_line`). The sandbox line plus an `assertion` object,
   in this order: `classification` (`pass | regression | new_ambiguity |
   changed | error`), `label` (`"now_parses"` only for an expected-no-parse
   assertion that now parses, else `null`), `missing` (expected parses hc did
   not produce, each a `[{"form", "gloss"}]` list), `unexpected` (actual parses
   nothing expected, same shape; `null` for one that could not be read), and
   `error_reason` (`invalid_segment`, `not_expressible`, `error_no_output`,
   `not_reached` or `timeout`; `null` unless `classification` is `error`).
   On a test line `parse.analyses` holds the **unmatched actual** parses only --
   the ones hc prints on a failure -- so it is `[]` on a pass, and
   `analysis_count` is hc's actual parse count. An `error` line's `parse`
   carries the error outcome with `analyses: null`.

Rule 1 of section 9 covers all of it: a reader that ignores unknown keys reads
a CP5 record -- either spine -- exactly as it read a CP3 or CP4 one, and a
reader that does not know `spine` sees an in-process run, which is what a
pre-CP5 record is. Rule 2 applies to the sandbox line as to any other. And
nothing here is written inside a FieldWorks project folder (CP5 FR-042, FR-043):
the record, the cache, the sandboxes and the project copy all live outside it.
