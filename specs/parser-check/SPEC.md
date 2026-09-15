# SPEC -- parser-check: let the MCP run HermitCrab and verify its own work

**Feature:** `parser-check`
**Repo:** FlexToolsMCP
**Status:** spec, not implemented
**Filed issues:** (none yet)
**Source:** user-contributed `hcparse.ps1` (repo root), 2026-09-15
**Author:** Claude Code, with matthew_lee@sil.org
**Depends on:** nothing new; builds on `project_discovery`, `project_access`,
`subprocess_helpers`, `op_telemetry`, and the `tool-responses/1.0` contract

---

## 1. Context

The MCP can already change a lexicon and a morphology: entries, allomorphs,
environments, MSAs, phon rules, strata (`FLExProject` exposes `Allomorphs`,
`MorphRules`, `PhonRules`, `PhonFeatures`, `Strata`, `NaturalClasses`,
`Environments` -- `flexicon_api_v4.8.0.json`). What it cannot do is tell
whether any of that was *linguistically* correct.

`run_module` reporting `[OK] Operation completed successfully` means the Python
ran and LCM accepted the write. It says nothing about whether the affix you just
added actually lets `membaca` parse, or whether the environment you tightened
just broke forty words that used to parse. Today the only way to find out is for
the human to open FLEx, run the parser by hand, and eyeball it.

A user has supplied `hcparse.ps1`, which closes that gap from the command line:
it copies a FLEx project, runs FieldWorks' `GenerateHCConfig.exe` over the copy
to produce a HermitCrab configuration, writes an HC command script, and runs the
standalone HermitCrab tool (`hc.dll` under `dotnet`) against a word list.

That is the missing verification primitive. This spec turns it into MCP tools so
the loop becomes:

```
parse (baseline) -> run_module edits the grammar -> parse (current) -> diff
                                                                        |
                                            "3 words fixed, 0 broken"   |
                                            "1 word broken: see trace" <-+
```

**The point of this feature is the arrow back.** A parse that only reports
"42 of 60 parsed" is a number. A parse that reports "your change fixed
`mengambil` and broke `menulis`, and here is the HermitCrab trace showing which
rule blocked it" is verification.

---

## 2. Settled -- do not revisit

Decided with the maintainer, 2026-09-15:

- **S1. Both jobs, not one.** The feature ships one-shot parsing *and*
  before/after diffing. Diffing is not a phase-2 nice-to-have; it is the reason
  the feature exists (section 1).
- **S2. Word lists for `text` / `genre` / `all_texts` scopes come from wordform
  occurrences**, walking the interlinear structure -- not from raw tokenization
  of baseline paragraph text. Consequences are spelled out in section 6.3.
- **S3. The HermitCrab config is cached, keyed on the `.fwdata` identity
  (mtime + size) plus generator identity.** Regenerating on every parse is
  unusable: it copies the whole project and shells out to a .NET generator.
- **S4. PowerShell is the execution mechanism.** Every user is on Windows. The
  bundled script stays PowerShell; the MCP does not reimplement HermitCrab
  invocation in Python.
- **S5. Parsing is read-only, always.** No parse path ever writes to the live
  project, and no parse result is ever written back into the database (see
  non-goals, section 15). All three tools are annotated `READ_ONLY_SAFE`.
- **S6. The parse operates on a copy.** Config generation reads a copied
  `.fwdata`, never the live one, so a FLEx instance holding the project is
  undisturbed. This is already how `hcparse.ps1` behaves and it is correct.

---

## 3. Prior art: what `hcparse.ps1` already got right

The submitted script encodes four hard-won lessons. The bundled version must
preserve all of them, and the spec records *why* so a later refactor does not
quietly drop one.

| Behaviour in the script | Why it is there |
|---|---|
| Copy the project before generating | A running FLEx holds `.fwdata`; `GenerateHCConfig.exe` against the live file is a lock fight at best |
| `Get-Content $WordFile -Encoding UTF8` | PS 5.1 defaults to the ANSI code page for a BOM-less file. Without this, any non-Latin word list becomes mojibake and HermitCrab reports "invalid segment at position 1" for **every** word -- a total failure that looks like a grammar problem |
| `UTF8Encoding($false)` when writing the HC script | HC reads the script as UTF-8; a BOM corrupts the first command |
| Split `-Words` on `[,\s]+` | Under `powershell -File`, a comma-separated list arrives as one string |
| `tracing on` / `stats -p` | The only machine-visible "why" HermitCrab offers |

### 3.1 What it lacks for MCP use

| Gap | Impact |
|---|---|
| Output is prose on stdout | Nothing to build a diff on |
| `$fw` and `$hcTool` hardcoded | Breaks on any non-default install |
| `& dotnet ...` with no `$LASTEXITCODE` check | A failed parse run looks like a successful empty one |
| `& .\GenerateHCConfig.exe ... \| Out-Null` | Discards exactly the diagnostic the user asked to be able to read |
| No timeout | A pathological grammar hangs the MCP's subprocess slot |
| Temp files leak on throw (no `try/finally`) | Litter in `%TEMP%`, and the copied project can be hundreds of MB |
| Words passed on the command line | Quoting, length, and encoding hazards for arbitrary orthographies |
| No config reuse across runs | Every parse pays the full copy + generate cost |

Section 9 is the hardening delta.

---

## 4. Architecture

Three layers, each independently testable.

```
  flextools_parse(scope=...)
          |
  L1  scope resolution        Python, in-process, read-only subprocess runner
          |                   -> deduped word list + scope_fingerprint
          v
  L2  parse execution         PowerShell: hcparse.ps1 (bundled, hardened)
          |                   -> run artifact directory
          v
  L3  result parsing + diff   Python
          |                   -> structured MCP response
          v
  flextools_parse_log / flextools_parse_diff
```

### 4.1 L1 -- scope resolution

Runs through the **existing** read-only execution path
(`handlers/execution.py` -> `subprocess_helpers.run_script_async`), with an
internally generated snippet. It is not a new project-opening mechanism: it
inherits the lock handling, the `project_locked` / `project_drive_unavailable`
diagnostics, the timeout, and the process-tree kill that path already has.

The snippet is MCP-authored and fixed, so it bypasses the LLM-facing discovery
and casting gates (it is not user code). It is still read-only and still runs
under the same runner.

### 4.2 L2 -- parse execution

Bundled at `src/flextoolsmcp/scripts/hcparse.ps1`, shipped in the wheel
(`MANIFEST.in` + `package_data`). Invoked as:

```
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <hcparse.ps1> ...
```

`-NoProfile` is not optional: a user profile that prints a banner lands in
stdout and corrupts any output parsing.

### 4.3 L3 -- artifacts

Every parse run gets a directory:

```
~/.flextoolsmcp/parse/
  config-cache/<project>/<cache_key>/hc-config.xml
  config-cache/<project>/<cache_key>/key.json
  runs/<project>/<run_id>/
      run.json              # machine-readable: inputs, timings, exit codes, results
      words.txt             # UTF-8, one word per line -- the exact input
      hc-script.txt         # the HC command script as executed
      hc-output.txt         # HC's -o output file
      hc-stdout.txt         # HC console output
      generate-config.log   # GenerateHCConfig stdout+stderr (see 3.1)
      trace.txt             # present only when tracing ran (section 8.2)
```

`run_id` is `<UTC yyyymmddTHHMMSSZ>-<8 hex>`. Retention: keep the newest 20 runs
per project, prune oldest (mirrors `backup.py::_prune_old_backups`, and the
lexicographic-sort-is-chronological-sort trick applies here too).

---

## 5. Tools

Three new tools. Names follow the existing `flextools_*` convention; all are
registered in `tool_definitions.py` / `dispatch.py` like every other tool.

### 5.1 `flextools_parse`

Resolve a scope to words, parse them, return a summary plus a `run_id`.

| Arg | Type | Default | Notes |
|---|---|---|---|
| `project_name` | str | session project | Resolved through `project_discovery` fuzzy matching, same as `run_module` |
| `scope` | enum | `words` | `words` \| `text` \| `genre` \| `all_texts` \| `all_wordforms` |
| `words` | list[str] | -- | Required when `scope="words"` |
| `text_name` | str | -- | Required when `scope="text"` |
| `genre` | str | -- | Required when `scope="genre"` |
| `limit` | int | 500 | Cap on resolved words. See 6.5 |
| `min_occurrences` | int | 1 | Skip wordforms rarer than this |
| `include_baseline_tokens` | bool | false | Opt-in fallback for unanalyzed segments. See 6.3 |
| `trace` | enum | `on_failure` | `off` \| `on_failure` \| `all`. See 8.2 |
| `config_policy` | enum | `auto` | `auto` \| `reuse` \| `rebuild` |
| `label` | str \| null | null | Human tag, e.g. `"before affix fix"` -- shows up in run listings and diffs |
| `timeout_seconds` | int | 300 | Whole parse, config generation included |

Returns (success envelope, `_contract: tool-responses/1.0`):

```json
{
  "status": "ok",
  "run_id": "20260915T142233Z-a1b2c3d4",
  "label": "before affix fix",
  "project": "Indonesian-HermitCrab",
  "scope": {"kind": "genre", "genre": "Narrative",
            "matched_texts": ["Kancil dan Buaya", "Asal Mula"],
            "fingerprint": "sha256:..."},
  "words": {"resolved": 412, "parsed_ok": 355, "no_parse": 57,
            "truncated_by_limit": false},
  "coverage": {"segments_seen": 1204, "segments_unanalyzed": 91,
               "note": "91 segments have no interlinear analysis and contributed no words"},
  "config": {"source": "cache", "cache_key": "...", "generated_at": "..."},
  "staleness": "fresh",
  "timings_s": {"scope": 4.1, "config": 0.0, "parse": 22.7},
  "failures_preview": [
     {"word": "menulis", "reason": "no_parse",
      "explanation": "no morphological rule produced a full parse",
      "trace_available": true}
  ],
  "next": ["flextools_parse_log(run_id=..., section='trace', word='menulis')",
           "flextools_parse_diff(baseline=..., current=...)"]
}
```

`failures_preview` is capped at 10. The full result set lives in `run.json` and
is reachable via `flextools_parse_log`. **The tool response must never inline the
whole word-by-word result set** -- a 500-word parse with traces is hundreds of KB
and would blow the caller's context for no benefit.

### 5.2 `flextools_parse_diff`

| Arg | Type | Default | Notes |
|---|---|---|---|
| `baseline` | str | -- | `run_id`, or `"latest"`, or a `label` |
| `current` | str | `"parse_now"` | `run_id`, or `"parse_now"` to run a fresh parse with the baseline's exact scope |
| `force` | bool | false | Diff across differing scopes (section 10.2) |
| `include` | enum | `changes` | `changes` \| `all` -- whether unchanged words appear |

`current="parse_now"` is the ergonomic path: edit, then
`flextools_parse_diff(baseline="before affix fix")` and the tool re-parses the
identical word list and diffs in one call.

Returns:

```json
{
  "status": "ok",
  "baseline": {"run_id": "...", "label": "before affix fix"},
  "current":  {"run_id": "...", "label": null},
  "verdict": "regression",
  "summary": {"fixed": 3, "broken": 1, "changed": 7, "unchanged": 401,
              "only_in_baseline": 0, "only_in_current": 0},
  "broken": [{"word": "menulis", "was": 1, "now": 0,
              "trace_available": true}],
  "fixed":  [{"word": "mengambil", "was": 0, "now": 1}],
  "changed":[{"word": "membaca", "was": 1, "now": 4,
              "note": "analysis count rose -- new ambiguity"}]
}
```

`verdict` is `regression` when `broken > 0`, `improvement` when
`fixed > 0 and broken == 0`, `ambiguity_shift` when only `changed > 0`, else
`no_change`.

**Ambiguity is a regression too.** A word going from one analysis to seven still
"parses" but the grammar got worse. `changed` exists to catch that; it must not
be collapsed into `unchanged`.

### 5.3 `flextools_parse_log`

This is the tool the maintainer specifically asked for: *read the logs to know
how/why it failed or worked*.

| Arg | Type | Default | Notes |
|---|---|---|---|
| `run_id` | str | `"latest"` | |
| `section` | enum | `summary` | `summary` \| `config_generation` \| `hc_stdout` \| `hc_output` \| `trace` \| `words` \| `results` |
| `word` | str \| null | null | Restrict `trace` / `results` to one word |
| `filter` | enum | `all` | `all` \| `failures` \| `successes` |
| `lines` | int | 200 | Tail cap, mirroring `GetOperationLogsInput.log_lines` |
| `offset` | int | 0 | For paging a long trace |

`section="config_generation"` answers the single most common real failure --
config generation silently produced nothing, so every word "fails". Under the
current script that output is thrown away by `| Out-Null`; the bundled version
must capture it (section 9).

### 5.4 Extension to `flextools_health`

Add a `parser` block to the existing health probe:

```json
"parser": {
  "hc_tool": {"found": true, "path": "C:\\Users\\x\\AppData\\Local\\HermitCrabTool\\hc.dll"},
  "dotnet":  {"found": true, "version": "8.0.11"},
  "generate_config": {"found": true, "path": "C:\\Program Files\\SIL\\FieldWorks 9\\GenerateHCConfig.exe"},
  "powershell": {"found": true, "version": "5.1.26100.1"},
  "cached_configs": 2,
  "ready": true
}
```

Cheap, filesystem-only, no subprocess. This is how a user finds out the tool is
not installed *before* burning five minutes on a copy-and-generate that was
never going to work.

---

## 6. Scope resolution (settled decision S2)

### 6.1 The walk

For `text`, `genre`, and `all_texts`, words come from the interlinear structure,
using flexicon facades that already exist (verified against
`flexicon_api_v4.8.0.json`):

```
project.Texts.GetAll()                    -> IText
  [filter by name or genre]
project.Paragraphs.GetAll(text)           -> IStTxtPara
project.Segments.GetAll(paragraph)        -> ISegment
project.Segments.GetAnalyses(segment)     -> list[IAnalysis]   <-- polymorphic
  [normalize each token to its owning IWfiWordform]
project.Wordforms.GetForm(wordform)       -> str
```

### 6.2 The IAnalysis polymorphism

`Segments.GetAnalyses()` returns `IAnalysis` tokens, which at runtime are
`IWfiWordform`, `IWfiAnalysis`, or `IWfiGloss` depending on how far the human
interlinearized that token. Normalization:

- `IWfiWordform` -> itself
- `IWfiAnalysis` -> `project.WfiAnalyses.GetOwningWordform(a)`
- `IWfiGloss` -> owning analysis -> owning wordform
- punctuation tokens -> skipped

This is precisely the shape the casting index exists for, and flexicon has met
it before -- `SegmentOperations.GetGloss` is documented as returning `''` "for
token types that carry no chosen word gloss". The implementation must go through
`resolve_property` / `casting_helpers` rather than assuming a concrete type, or
it will `AttributeError` on the first partially-glossed text.

### 6.3 The honest limitation of S2

Occurrence-based selection means **a segment nobody has interlinearized
contributes nothing.** In a project where the texts are typed but not yet
analyzed, `scope="all_texts"` can legitimately resolve to zero words.

This is a feature, not a bug -- those are the words the user actually cares
about parsing -- but it must be *visible*, never silent:

- Every run reports `coverage.segments_unanalyzed`.
- Zero resolved words is an error (`parse_scope_empty`), not an empty success,
  and its hint names this cause first.
- Opt-in escape: `include_baseline_tokens=true` falls back to whitespace and
  punctuation tokenization of `Segments.GetBaselineText()` for segments with no
  analyses. Off by default, because naive tokenization of an unfamiliar
  orthography produces garbage words that then "fail to parse" and look like
  grammar bugs.

`scope="all_wordforms"` (`project.Wordforms.GetAll()`) is the cheap superset: the
project's entire wordform inventory, no text walk. It includes wordforms with
zero current occurrences (stale entries from deleted texts), so its numbers are
not comparable to a text-scoped run -- the `scope_fingerprint` guard in 10.2
enforces that.

### 6.4 Genre matching -- use `GenresRC`, not `GetGenre`

`TextOperations.GetGenre(text)` is documented as returning **the first** genre
only. A text tagged `[Narrative, Folklore]` scoped by `"Folklore"` would be
silently missed.

Genre scope must read the full reference collection `IText.GenresRC`
(`liblcm_api_v11.0.0.json`, `IText`) and match against every genre on the text.
Matching is case-insensitive against both the genre's name and its abbreviation,
in the default analysis writing system.

More than one genre matching the string is `parse_scope_ambiguous`, returning the
candidates rather than guessing. Same for `text_name`.

### 6.5 Ordering, dedup, limit

Resolved words are deduplicated (exact string match, after NFC normalization),
then ordered by descending occurrence count, then alphabetically. `limit`
truncates *after* that ordering, so a truncated run covers the most frequent
words. `truncated_by_limit: true` is set, and the `scope_fingerprint` records the
limit so a later diff cannot compare a truncated run against a full one without
`force`.

---

## 7. Config caching (settled decision S3)

### 7.1 The key

```
cache_key = sha256(
    fwdata_abspath,
    fwdata_size_bytes,
    fwdata_mtime_ns,
    generate_config_exe_path + its size + mtime,
    hcparse_ps1_version_constant
)
```

The generator and script identity are in the key so a FieldWorks upgrade or a
script change invalidates every cached config instead of serving a stale one.

Stored as `config-cache/<project>/<cache_key>/{hc-config.xml, key.json}`.
`key.json` records the inputs in plain text so a human can see why a cache
entry exists. Retention: 3 per project, LRU by access time.

### 7.2 Explicit invalidation beats mtime

Do not rely on mtime alone. Whenever `run_module` completes a **write** run
against a project, stamp that project's cache entries dirty immediately. It is
one file write, it is exact, and it removes the entire class of "I edited, the
parse used yesterday's grammar" bugs.

### 7.3 The shared-mode caveat -- this must be stated in the response

Per the confirmed root cause recorded in
`specs/swahili-audit-2026-09` (issue #96): when FLEx holds a project in shared
mode, a non-master peer's commit lands only in the in-memory shared commit log.
`.fwdata` advances **only when the master writes**, and a fresh open never
replays commit-log records.

Therefore, when FLEx is holding the project:

- `.fwdata` mtime/size can be unchanged even though the grammar *has* changed.
  The cache key is not just stale -- it is structurally incapable of noticing.
- Rebuilding the config does not help, because `GenerateHCConfig.exe` also reads
  `.fwdata`.

The only honest behaviour is to say so. Before every parse, consult
`project_access` for a verdict. When it is `shared` or `held_by_other`:

- set `staleness: "shared_mode_unverifiable"` in the response,
- carry a `note`: *"FLEx is holding this project. The parse reflects the last
  state saved to .fwdata, which may predate recent edits. Save in FLEx (or close
  it) and re-run for a verified result."*
- and in a `flextools_parse_diff`, refuse to report `verdict: "no_change"` as
  reassurance -- downgrade it to `"no_change_unverifiable"`.

**Never promise a safe read-back interval.** There is no N seconds that is safe;
the staleness window is unbounded and human-gated.

---

## 8. Reading the logs (the "how/why" requirement)

### 8.1 Failure taxonomy

Every word in `run.json` gets a result record:

```json
{"word": "menulis", "parsed": false, "analyses": [],
 "failure": {"reason": "no_parse", "stage": "morphology",
             "explanation": "...", "trace_offset": 4211}}
```

Minimum `reason` vocabulary, ordered by how often it actually bites:

| reason | What it really means | First thing to tell the user |
|---|---|---|
| `invalid_segment` | A character is not in the phoneme inventory | Usually encoding (see the UTF-8 lesson, section 3) or a genuinely unlisted grapheme -- check the writing system, not the grammar |
| `no_parse` | Nothing produced a complete parse | The grammar gap the user is hunting |
| `no_lexical_entry` | Root not found in the lexicon | Add the entry, or check the citation form's morph type |
| `config_error` | HC rejected the configuration | Not a word problem; see `section='config_generation'` |
| `timeout` | Parse exceeded the budget | Often a runaway rule; the trace shows the loop |

`config_error` and `timeout` are run-level, not word-level, and must surface as
error envelopes (section 11), not as 500 quiet word failures.

### 8.2 The two-pass trace

`tracing on` emits HermitCrab's full rule-application record for every word.
Across 500 words that is megabytes, and 95% of it describes words that parsed
fine and that nobody will ever read.

Default `trace="on_failure"` runs two passes:

1. **Pass 1, untraced:** parse the whole word list. Fast, small output.
2. **Pass 2, traced:** re-run *only* the words that failed, with `tracing on`,
   capped at 25 words (configurable `parser.trace_cap`). Write to `trace.txt`
   with a per-word byte offset recorded in `run.json` so
   `flextools_parse_log(section='trace', word='menulis')` can seek instead of
   scanning.

`trace="off"` skips pass 2. `trace="all"` traces the whole list in one pass and
is documented as expensive.

When more than `trace_cap` words failed, the run says so explicitly:
`"57 words failed; traced the first 25. Re-run with a narrower scope for the
rest."` Silently tracing a subset and not saying so is how a user concludes a
word has no trace when it simply was not traced.

### 8.3 From trace to explanation

Where the trace is parseable, `failure.explanation` should name the blocking
rule or the failed stage in one line. Where it is not, return the raw trace
slice and say it is raw. Fabricating a linguistic explanation from an
unrecognized trace format would be worse than useless -- it would be a confident
wrong answer about someone's grammar.

The trace grammar is the largest genuine unknown in this spec; see section 14.

### 8.4 Telemetry

Parse runs close into the existing `operations.jsonl` with
`op_kind: "parse"` and fields `run_id, project, scope_kind, words_resolved,
parsed_ok, no_parse, config_source, duration_s, outcome`. That keeps
`flextools_get_operation_logs` a single front door for "what has this session
done", and gives the diagnostic-report feature something to attach.

---

## 9. Hardening delta for `hcparse.ps1`

The bundled `src/flextoolsmcp/scripts/hcparse.ps1` starts from the submitted
script and applies:

| # | Change | Reason |
|---|---|---|
| H1 | `-FieldWorksDir` parameter, resolved by the caller via `versioning._default_liblcm_search_paths()`; `-HcToolPath` parameter with config override `parser.hc_tool_path` | Hardcoded `C:\Program Files\SIL\FieldWorks 9` and `%LOCALAPPDATA%\HermitCrabTool` break non-default installs |
| H2 | Words are passed **by file only** (`-WordFile`), never on the command line | Arbitrary orthographies plus PowerShell quoting is a losing game; also removes a command-line length ceiling |
| H3 | Write `run.json` with inputs, exit codes, timings, and per-word results | L3 must not screen-scrape prose |
| H4 | Check `$LASTEXITCODE` after `GenerateHCConfig.exe` **and** after `dotnet hc.dll`; non-zero is a hard failure with the captured log | Today a failed run is indistinguishable from an empty successful one |
| H5 | Redirect `GenerateHCConfig` output to `generate-config.log` instead of `Out-Null` | This is the diagnostic the user explicitly asked to be able to read |
| H6 | Wrap temp/copy lifecycle in `try/finally`; delete the copied project after config generation unless `-KeepCopy` | A throw currently leaks a full project copy into `%TEMP%` |
| H7 | Free-space preflight before the copy: require >= 2x project size | Mirrors `backup.py`'s existing rule; a failed mid-copy is worse than a refusal |
| H8 | `-TimeoutSeconds`, enforced around the `dotnet` call | A runaway grammar must not pin an MCP subprocess slot |
| H9 | ASCII-only console output; no emoji, no box-drawing | Repo convention (CLAUDE.md), and these strings get parsed |
| H10 | `-ConfigOut` so the caller places the config directly in the cache directory | Avoids a second copy of a large XML |
| H11 | Preserve verbatim: the UTF-8 no-BOM script write, `-Encoding UTF8` on `Get-Content`, `[,\s]+` splitting | Section 3 -- these are bug fixes, not style |
| H12 | `$script:HCPARSE_VERSION` constant, bumped on any behavioural change | Feeds the config cache key (7.1) |

The original `hcparse.ps1` stays at the repo root as the contributed reference
until CP2 lands, then is removed in favour of the bundled copy, with a
`CHANGELOG` note crediting the contribution.

---

## 10. Diff semantics

### 10.1 Alignment

Diff aligns on the word string (NFC-normalized). Per word, comparing baseline
analysis count `b` to current `c`:

| Condition | Bucket |
|---|---|
| `b == 0, c > 0` | `fixed` |
| `b > 0, c == 0` | `broken` |
| `b > 0, c > 0`, analysis sets differ | `changed` |
| identical | `unchanged` |

Words present in only one run go to `only_in_baseline` / `only_in_current` and
never into `fixed` / `broken` -- a word that was not tested cannot have been
fixed.

Analysis-set comparison is on the normalized morpheme sequence (form + gloss +
type per morph), not on raw trace text, so cosmetic output changes do not read
as grammar changes.

### 10.2 The scope guard

A diff is only meaningful across identical inputs. Each run stores a
`scope_fingerprint = sha256(scope_kind, scope_target, limit, min_occurrences,
sorted(word_list))`.

Mismatched fingerprints are **refused** with `parse_scope_mismatch` unless
`force=true`, and under `force` the diff is computed on the intersection only,
with the exclusions reported. Comparing 412 narrative words against 3,000
inventory wordforms and reporting "2,588 fixed" is exactly the kind of confident
nonsense this guard exists to prevent.

---

## 11. Error codes (contract extension)

Appended to `docs/TOOL-CONTRACT.md`. All additive, so the contract stays at
`tool-responses/1.0`; the stability promise requires a CHANGELOG entry under
**"Tool contract"**.

| Error code | Detail fields |
|---|---|
| `parser_tool_missing` | `component` (`hc_tool` \| `dotnet` \| `generate_config` \| `powershell`), `expected_path`, `install_hint` |
| `parser_config_failed` | `exit_code`, `stderr_tail`, `log_path`, `run_id` |
| `parser_timeout` | `timeout_seconds`, `words_completed`, `run_id`, `hint` |
| `parse_scope_empty` | `scope`, `matched_texts`, `segments_unanalyzed`, `hint` |
| `parse_scope_ambiguous` | `scope`, `requested`, `candidates` |
| `parse_scope_mismatch` | `baseline_fingerprint`, `current_fingerprint`, `differing_fields`, `hint` |
| `parse_run_not_found` | `run_id`, `available_runs` |

Reused unchanged: `project_not_found`, `project_locked`,
`project_drive_unavailable`, `project_path_mismatch`.

`parser_tool_missing` must carry a real install hint, not a shrug. Most users
will not have the standalone HermitCrab tool installed, and this error is the
one they will hit first.

---

## 12. Safety

- **No writes, ever.** All three tools are `READ_ONLY_SAFE`. `write_enabled` is
  irrelevant to them and is not consulted.
- **The live project is never opened for write**, and config generation runs on
  a copy (S6).
- **Disk:** a project copy can be hundreds of MB. Free-space preflight (H7); the
  copy is deleted after generation (H6); only the config XML is retained, under
  a bounded cache (7.1).
- **Subprocess:** reuse `subprocess_helpers.run_script_async`, which already does
  `taskkill /T /F` on Windows -- necessary here because `dotnet` spawns
  grandchildren.
- **No `Invoke-Expression`** anywhere in the script; word data reaches
  PowerShell only through a file (H2).
- **Untrusted content:** words come from the user's own project, and HC output
  from a local tool. Neither is treated as instructions; both are data in the
  response.

---

## 13. Checkpoints

| CP | Deliverable | Exit criteria |
|---|---|---|
| **CP1** | Parser preflight: detection helpers + the `parser` block in `flextools_health`. No parsing. | Health reports `ready: true/false` correctly on a machine with and without the HC tool; `parser_tool_missing` details are exercised by unit tests |
| **CP2** | Hardened `hcparse.ps1` (section 9) + `flextools_parse` with `scope="words"` only | A caller-supplied word list parses end to end and produces a complete run artifact directory; H4 exit-code checks proven by a deliberately broken config |
| **CP3** | Scope resolution (`text`, `genre`, `all_texts`, `all_wordforms`) + config cache (section 7) incl. the shared-mode caveat | Genre scope finds a text via its second genre (6.4); cache hit skips config generation; a write run invalidates the cache (7.2) |
| **CP4** | `flextools_parse_log` + two-pass trace (8.2) | `section='config_generation'` surfaces a real generator failure; per-word trace seek works on a >10MB trace |
| **CP5** | `flextools_parse_diff` (section 10) + telemetry + `docs/TOOL-CONTRACT.md` + CHANGELOG + user docs | Live before/after run: a deliberate grammar break is reported as `verdict: "regression"` naming the right word |

CP5 requires live verification (`lex-verification`) against a project with a
working HermitCrab grammar -- **not** Sena 3 unless it is confirmed to have one.
The contributor's `Indonesian-HermitCrab` is the known-good candidate and should
be obtained or reproduced before CP5 starts. A CP5 that claims green without a
live parse is a failed CP5.

---

## 14. Open questions

1. **HermitCrab output grammar.** The exact stdout/`-o` format, and the trace
   format, are unknown to this spec. CP2 must begin by capturing real output
   from a working project into `tests/fixtures/hc/` and building the parser
   against those fixtures. Do not write the output parser from assumption.
2. **Does `GenerateHCConfig.exe` ship in every FieldWorks 9 install,** or only
   some builds/versions? Affects whether `parser_tool_missing` is a rare edge or
   the common case.
3. **Where does `hc.dll` come from?** The script expects
   `%LOCALAPPDATA%\HermitCrabTool\hc.dll`, which is not a standard FieldWorks
   path. The install story needs documenting before users meet
   `parser_tool_missing`.
4. **Genre names and localization.** Genre possibility lists can be localized.
   Matching against the default analysis WS (6.4) may miss a user working in a
   localized UI. Revisit if it bites.
5. **`.fwdata` vs. other backends.** This assumes a file-based project. A
   Send/Receive or remote-backend project may need a different config path.

---

## 15. Non-goals

- **XAmple.** FLEx's other parser is out of scope. The tool names are
  deliberately generic (`flextools_parse`, not `flextools_hc_parse`) so an
  `engine="xample"` argument can be added later without a rename.
- **The in-GUI FLEx parser service.** We shell to the standalone tool; we do not
  drive FLEx.
- **Writing parse results back into the project** (approving analyses, creating
  `IWfiAnalysis` records from HC output). That is a write path with its own
  gates and its own spec. Parsing stays read-only (S5).
- **Grammar authoring or rule suggestion.** Reporting "`menulis` broke" is in
  scope. Proposing the rule change that fixes it is not, yet.
- **Cross-platform support.** Windows only (S4).
- **Parsing text the project has not interlinearized**, beyond the opt-in
  fallback in 6.3.

---

## 16. Test plan

**Unit (no FieldWorks required)**
- Scope resolution against a recorded fixture of the texts/paragraphs/segments/
  analyses walk, including: a text whose matching genre is second in `GenresRC`;
  a segment with zero analyses; `IWfiGloss` and `IWfiAnalysis` tokens alongside
  bare `IWfiWordform` tokens; punctuation tokens.
- HC output parser against captured fixtures (question 1), including a
  `config_error` capture and an `invalid_segment` capture.
- Cache-key computation: stability across calls, change on mtime, change on
  generator mtime, change on script version.
- Diff alignment: every bucket in 10.1, plus the `only_in_*` cases and the
  `parse_scope_mismatch` refusal.
- Error envelopes: every code in section 11 validates against its detail model
  (`extra="forbid"`).

**Integration (Windows + FieldWorks, no HC tool)**
- `flextools_health` reports `parser.ready: false` with an actionable hint.
- `flextools_parse` fails fast with `parser_tool_missing` and does **not** copy
  the project first.

**Live (`lex-verification`, HC-configured project)**
- Non-Latin word list round-trips correctly -- the encoding regression in
  section 3 must have a standing test, since its failure mode (every word
  "fails") looks like a grammar problem and would otherwise be misdiagnosed.
- Baseline parse -> deliberate grammar break via `run_module` -> diff reports
  `regression` naming the right word -> revert -> diff reports `improvement`.
- Cache invalidation after that write run actually took effect (7.2).
- Shared-mode run (FLEx open) returns `staleness: "shared_mode_unverifiable"`.
