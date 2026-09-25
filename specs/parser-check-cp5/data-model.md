# Data Model: parser-check CP5 -- the sandbox spine

Every change to a shipped structure is **additive**, per CP3 `contracts/artifact.md` section 9.
Readers ignore unknown keys and tolerate a truncated last JSONL line. Paths are relative to the
sandbox root `~/.flextoolsmcp/parse/`, which `FLEXTOOLSMCP_PARSE_SANDBOX_DIR` overrides, unless a
path is shown as a run-record path.

Nothing in this model lives inside a FieldWorks project folder (FR-042). Each root is checked with
`assert_outside_project` when it is used.

---

## 1. The three lifecycles (FR-025)

| Artifact | Location | Owner | Lifecycle |
|---|---|---|---|
| **Project copy** | `work/<run_id>/` | system | Created after the free-space check. Deleted on every terminal path (research R-11) |
| **Cached config** | `config-cache/<project>/<cache_key>/` | system | Built at most once at a time per key. Invalidated on a write. Pruned to 3 per project, least recently used first. Never deleted while in use |
| **Sandbox config** | `sandboxes/<project>/<name>/` | **user** | Created on request. Never overwritten, invalidated or deleted by any code path |
| **Corpus** | `corpora/<project>/<name>.json` | **user** | Created by seeding. Same guarantees as a sandbox |

`<project>` is the project name, filesystem-escaped the way `backup.py` escapes it.

**Invariant, pinned by a test.** No function in `sandbox/cache.py` or `sandbox/workdir.py` accepts
a path under `sandboxes/` or `corpora/`. Each function that deletes files asserts that its target is
under `config-cache/` or `work/` before deleting.

## 2. Project copy (`work/<run_id>/`)

```
work/<run_id>/
  .flextoolsmcp-sandbox-work      # marker: {"run_id", "pid", "created_at", "source_fwdata"}
  <name>/<name>.fwdata            # allowlisted copy (R-11)
  <name>/WritingSystemStore/...   # allowlisted copy
```

- The sweep deletes only directories that hold the marker **and** whose `run_id` is not live in
  this server.
- The copy never holds `*.lock`. That is by construction, and a test pins it.

## 3. Cache entry (`config-cache/<project>/<cache_key>/`)

```
hc-config.xml
generate-config.log      # GenerateHCConfig's full stdout+stderr, verbatim (FR-009)
key.json
lcm-ids.json              # NEW (D4 reversed, FR-050): the validated id map for Try A Word shaping
```

**`lcm-ids.json`** (new, additive, CP5 re-plan correction 2026-09-24, D4 reversed, FR-050): written
server-side by a plain stream read of the byte-identical `work/<run_id>/` copy (never through LCM,
same mechanism as the `active_parser` check, R-02), mapping every id (`ID`/`ID2`/`InflTypeID`)
referenced by `hc-config.xml` to its LCM class:

```json
{
  "schema": "flextoolsmcp.hc-lcm-ids/1",
  "valid": true,
  "ids": {
    "4918": {"guid": "<hex>", "class": "MoStemAllomorph", "role": "form",
             "morph_type_guid": "<hex, MoForm only>", "form": "<text, MoForm only>"},
    "4919": {"guid": "<hex>", "class": "MoStemMsa", "role": "msa"}
  },
  "invalid_ids": [],
  "error": null,
  "vernacular_ws": "id-fonipa"
}
```

**`form` and `vernacular_ws` (added at T110, 2026-09-25, from the live SC-003 comparison).**
`GetMorphs` hands FLEx each morph's `IMoForm`, and FLEx shows that form's own text -- the
allomorph `meŋ` -- not the surface string the engine matched (`mem`); the surface is kept only for
a guessed root (`GuessedString`). The same stream read therefore records, for each form id, its
`Form` alternative in the project's default vernacular writing system (the first
`LangProject/CurVernWss` entry, recorded as `vernacular_ws`). A form with no text in that writing
system has no `form` key, and the worker then falls back to the surface string -- as it does for a
map written before these fields existed. Neither field affects `valid`.

`valid` is `false`, and `invalid_ids` lists every id that did not resolve to the expected class
(`MoForm` for `FormID`/`ID2`, `MoMorphSynAnalysis` for an MSA `ID`, `LexEntryInflType` for a
positive `InflTypeID`), when validation fails. A run against an invalid map fails as
`parser_job_failed` (`failure: "id_map_invalid"`) before any word is parsed, rather than shaping
silently wrong or skipping shaping. The sidecar's path is recorded in `key.json` (below) and
copied into a named sandbox at creation, the same way the rest of the cache entry's inputs are
(section 4).

`key.json`:

```json
{
  "schema": "flextoolsmcp.hc-cache/1",
  "cache_key": "<16 hex>",
  "inputs": {
    "fwdata_path": "C:\\...\\X.fwdata", "fwdata_size": 0, "fwdata_mtime_ns": 0,
    "generate_hc_config_path": "...", "generate_hc_config_size": 0, "generate_hc_config_mtime_ns": 0,
    "hcparse_version": "5.0.0"
  },
  "active_parser": "HC",
  "created_at": "<iso8601Z>",
  "last_used_at": "<iso8601Z>",
  "invalidated_at": null,
  "generation": {
    "exit_code": 0,
    "duration_ms": 0,
    "writing_completed": true,
    "load_errors": [{"kind": "invalid_environment", "line": "<verbatim>"}],
    "load_error_count": 0
  },
  "versions": {"generate_hc_config": "9.3.11.x", "fieldworks_hermitcrab": "3.8.2.0"},
  "hc_parameters": {
    "del_reapps": 0, "max_roots": 2, "merge_analyses": true, "guess_roots": true,
    "max_alternatives": 0
  },
  "lcm_ids_path": "lcm-ids.json"
}
```

**`hc_parameters` (new, additive, CP5 re-plan 2026-09-24).** The project's
`MorphologicalDataOA.ParserParameters/HC` values, read once at generation time and cached
alongside the config they describe -- **not exported by `GenerateHCConfig`**
(`reviews/research-cycle1-domain.md` section 1), so this is the only place they survive the
export. Each key defaults to FLEx's own default when the project's `ParserParameters` XML omits
it: `del_reapps=0`, `max_roots=2`, `merge_analyses=true`, `guess_roots=true`,
`max_alternatives=0`. `SandboxClient` reads `hc_parameters` as the first-preference source for the
sandbox worker's `--hc-params` (`contracts/sandbox-worker.md` section 6); a live `.fwdata` stream
read is the fallback when a cache entry predates this key (an old cache entry has no
`hc_parameters` at all -- additive, so an old reader and an old entry both still work; a run
against one falls through to the stream-read source, never to a refusal). A named sandbox
(user-edited `hc-config.xml`, no live project backing it once it diverges) has no `hc_parameters`
of its own; it copies `from_inputs` at creation the way it already copies the rest of the cache
entry's inputs (section 4 below), and that copy is what a `parse` against a named sandbox reads.

**`lcm_ids_path` (new, additive, CP5 re-plan correction 2026-09-24, D4 reversed, FR-050).** The
path, relative to the cache entry, of the `lcm-ids.json` sidecar that lets the sandbox worker
replicate FLEx's Try A Word morph-shaping rules. Like `hc_parameters`, it is copied into a named
sandbox at creation (section 4); an old cache entry that predates this key has no sidecar, and a
run against one is treated the same way a missing `hc_parameters` is -- fall through, here to "no
shaping applied", never to a refusal.

**Validation**
- `cache_key` equals `sha256(canonical(inputs))[:16]`.
- `load_error_count == len(load_errors)`.
- An entry is **usable** only if `invalidated_at` is null and `hc-config.xml` is non-empty.
- `last_used_at` is updated when a job starts using the entry.

**State**

```
(absent) --build under lock--> <key>.partial/ --rename--> usable
usable --write completes--> invalidated
invalidated --prune, refcount 0--> deleted
usable --prune, LRU rank > 3 and refcount 0--> deleted
```

## 4. Sandbox (`sandboxes/<project>/<name>/`)

```
hc-config.xml            # user-editable
origin.json              # written once at creation, never rewritten
lcm-ids.json             # copied from the source cache entry at creation (D4 reversed, FR-050)
```

**`lcm-ids.json`** is copied verbatim from the source cache entry's sidecar (section 3) at
creation time, the same way `origin.json`'s `from_inputs` copies the rest of the cache entry's
inputs. It is never regenerated or revalidated after copying: a hand-edit to `hc-config.xml` that
introduces a morph with no `ID` is exactly the user-added case FR-050 names, not a reason to
re-derive the map.

`origin.json`:

```json
{
  "schema": "flextoolsmcp.hc-sandbox/1",
  "name": "tighten-env",
  "project": "IndonesianHC-Complete",
  "created_at": "<iso8601Z>",
  "from_cache_key": "<16 hex>",
  "from_inputs": { "...": "a copy of the cache entry's inputs" },
  "sha256_at_creation": "<hex of hc-config.xml as created>"
}
```

**Name rule (FR-028).** A name must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`.

It must not be a Windows reserved device name (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`),
compared case-insensitively on the part before the first `.`. It must not end in `.` and must not
contain `..`. Then `resolve()` must stay under `sandboxes/<project>/`. That check is kept even
though the regex already excludes separators.

**Derived at run time, never stored:**
- `edited`: the current sha256 differs from `sha256_at_creation`.
- `predates_project_grammar` (FR-029): `from_cache_key` differs from the key the project's current
  inputs would give. This needs only a `stat`, and the project is not opened.

## 5. Corpus (`corpora/<project>/<name>.json`)

```json
{
  "schema": "flextoolsmcp.hc-corpus/1",
  "name": "baseline-2026-09-24",
  "project": "IndonesianHC-Complete",
  "created_at": "<iso8601Z>",
  "seeded_from": {"run_id": "<32 hex>", "config_source": {"kind": "project_cache", "cache_key": "..."}},
  "assertions": [
    {"word": "membaca", "expected": [[{"form": "mem", "gloss": "ACT"}, {"form": "baca", "gloss": "read"}]]},
    {"word": "xyz", "expected": []}
  ]
}
```

**Validation, when a corpus is run:**
- `schema` must be known;
- each `word` must be a non-empty string;
- `expected` is a list of parses, each parse a **non-empty** list of `{form, gloss}` strings;
- `expected: []` means "no parse";
- a malformed file is refused whole with `parse_sandbox_refused` (`reason: corpus_invalid`), naming
  the JSON path of the first fault;
- a well-formed assertion that is not expressible (FR-027) is **not** refused. It becomes an
  `error` result with `reason: not_expressible`, and the rest of the corpus runs.

Duplicate words are de-duplicated after NFC, keeping the first. The duplicates are listed in the
response.

## 6. Run record additions (`<record_dir>/<run_id>/`)

### 6.1 `RunMeta`: two new optional fields (F-12)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `spine` | `"in_process" \| "sandbox" \| null` | `null` | `null` is read as `"in_process"`, so every pre-CP5 run reads correctly |
| `sandbox` | object \| null | `null` | See 6.2. Present only on sandbox runs |

### 6.2 The `sandbox` meta section

**Revised (CP5 re-plan 2026-09-24).** The `hc_source`, `versions.hc_tool` and `version_skew` keys
are retired (there is one engine now, not two versions to compare -- `contracts/tools.md` section
6); the `hc` sub-object (hc's own exit code / timing) is retired along with the retired
Parse/Test spine, replaced by `worker` (the sandbox worker process's own outcome). Four keys are
new: `parser_parameters` (the resolved input), `parameters_applied` (what the loaded engine
actually accepted), `parameters_source`, and `engine_version` (promoted out of `versions` since it
is now the only engine version there is to report, not one of several).

```json
{
  "mode": "parse | test",
  "config_source": {"kind": "project_cache", "cache_key": "..."} ,
  "config_source_alt": {"kind": "named_sandbox", "name": "tighten-env", "edited": true, "predates_project_grammar": false},
  "corpus": {"name": "...", "assertion_count": 0} ,
  "versions": {"fieldworks_hermitcrab": "3.8.2.0", "generate_hc_config": "9.3.11.x", "hcparse": "5.0.0"},
  "engine_version": "3.8.2.0",
  "parser_parameters": {
    "del_reapps": 0, "max_roots": 2, "merge_analyses": true, "guess_roots": true,
    "max_alternatives": 0
  },
  "parameters_applied": ["del_reapps", "max_roots", "merge_analyses", "guess_roots"],
  "parameters_source": "cache_key_json | fwdata_stream_read | flex_defaults",
  "generation": {"reused_cache": true, "cache_key": "...", "load_error_count": 0, "load_errors": []},
  "copy": {"bytes": 0, "cleanup": "deleted | failed | not_made", "path_if_failed": null},
  "worker": {"exit_code": 0, "timed_out": false, "in_flight_index": null, "duration_ms": 0, "counters": "ok | unavailable_timeout"},
  "shaping": {"applied": true, "id_map": "valid | invalid | absent"},
  "truncated_by_limit": false,
  "advisories": ["sandbox_predates_project_grammar", "grammar_load_errors"]
}
```

**`shaping`** (new, additive, CP5 re-plan correction 2026-09-24, D4 reversed, FR-050). `id_map` is
`"valid"` when the cache entry's `lcm-ids.json` validated cleanly and shaping rules a-d were
applied against it; `"invalid"` only appears on a failed run (`parser_job_failed`, `failure:
"id_map_invalid"`) and is recorded even though the run produced no word results, so the failure
reason survives in the record; `"absent"` covers a cache entry that predates the sidecar (no
`lcm_ids_path` in `key.json`), in which case `applied` is `false` and no shaping rule is applied at
all, never a refusal.

`config_source` takes one of two shapes: `{"kind": "project_cache", ...}` or
`{"kind": "named_sandbox", ...}`. The snippet shows both only for illustration; a real record holds
exactly one under the single key `config_source`. `corpus` is present only when `mode == "test"`.

**`parser_parameters`** is the resolved Morpher settings `SandboxClient` sent to the worker at
spawn (`contracts/sandbox-worker.md` section 6), always all five keys, each already defaulted.
**`parameters_applied`** is the subset the loaded engine actually exposed and accepted --
`max_alternatives` is absent against the bundled FieldWorks 9.3.11 engine (v3.8.2.0), which has no
such property (`reviews/research-cycle1-domain.md` section 1, `[verified v3.8.2]`); a mismatch
between the two lists is expected and is not an error. **`parameters_source`** names which of the
three D3 sources (`data-model.md` section 3) won for this run: a cache entry's `hc_parameters`, a
live `.fwdata` stream read, or FLEx's own defaults (only when neither of the first two had a
project to read from -- a named sandbox with no live project backing it, for example).
**`engine_version`** is the `FileVersion` D7's health check already reports (section 7 below),
repeated here per-run so a run record is self-describing without cross-referencing a health
snapshot taken at a different time.

**Also on a sandbox run.** The existing `scope_fingerprint` is set with `scope_kind: "words"`
and `engine: "HC"` (R-14). The existing `project_state.staleness` is set on the R-13 verdicts. The
existing `counters` and `counter_divergences` fields are filled from the worker's own tally
(section 6.6's `engine_counters`, replacing hc's `stats -p`/`stats -t` output as the source).

### 6.3 Sandbox files in the run directory

**Revised (CP5 re-plan 2026-09-24).** The Parse/Test `hc`-script era wrote a script, a per-word
dispatch, and a decoded console stream (`contracts/hcparse.md` section 6, retired). The sandbox
worker exchanges structured JSON over stdio, one message per line, so there is no script to write
and no console stream to decode -- only its own stderr diagnostics and the config it loaded remain
worth keeping per run.

```
<run_id>/sandbox/
  generate-config.log   # copied from the cache entry; on a warm run, prefixed by one line naming the reuse
  worker-stderr.txt     # the sandbox worker's own diagnostics (UTF-8); the `_log` stream, never the protocol
  run.json              # the sandbox run's hand-off: worker exit status, engine_version, parameters_applied
```

Each file is written through `RunRecord._child`, which blocks absolute paths and `..`.

### 6.4 `results.jsonl`: the sandbox line

This is CP3's line shape with additive keys. `parsed` and `analysis_count` keep their meanings.

```json
{
  "index": 0,
  "wordform": "membaca",
  "parse": {
    "parsed": true,
    "analysis_count": 1,
    "outcome": "parsed",
    "analyses": [
      {
        "signature": null,
        "rendered_morphs": ["mem", "baca"],
        "morphs": [{"form": "mem", "gloss": "ACT", "guessed": false, "is_circumfix": false, "user_added": false}, {"form": "baca", "gloss": "read", "guessed": false, "is_circumfix": false, "user_added": false}],
        "guessed": false,
        "readable": true,
        "raw": null
      }
    ],
    "position": null,
    "flags": []
  }
}
```

**`outcome`** is a closed enum (FR-018):

| `outcome` | `parsed` | Notes |
|---|---|---|
| `parsed` | true | |
| `not_parsed` | false | |
| `invalid_segment` | false | `position` is set |
| `not_expressible` | false | Never sent |
| `error_no_output` | false | The word in flight at a crash or timeout |
| `not_reached` | false | Not processed because of a timeout, crash or cancel |

`parsed` is true only for `parsed`. An analysis that could not be read has `readable: false` and
keeps both raw lines in `raw`; `morphs` and `rendered_morphs` are then null (FR-019).
~~**`flags`** may contain `leading_dash_unverified` (R-09).~~ **Retired (CP5 re-plan
2026-09-24).** `leading_dash_unverified` existed only for the retired hc-script quoting rules
(`contracts/hcparse.md` section 4); a wordform now travels as a plain JSON string field to the
sandbox worker, so `flags` is always `[]` for a sandbox-worker line.

**`morphs[].guessed`** (new, D5, CP5 re-plan 2026-09-24): per-morph, `true` when that morph is a
synthesised guess (`word.GetAllomorph(morph).Guessed`,
`reviews/research-cycle1-domain.md` section 3 -- the reliable signal, not a gloss-equals-form
heuristic). **`analyses[].guessed`** (new, same source) is `true` if any morph in that analysis is
guessed, a per-analysis roll-up so SC-003(b)'s "guessed-root analyses compared as their own
category" needs no per-morph scan to answer.

**`morphs[].is_circumfix`** (new, additive, CP5 re-plan correction 2026-09-24, D4 reversed,
FR-050): `true` only for the emitted (second) occurrence of an `AffixProcessAllomorph`-with-no-`ID2`
circumfix pair (rule b/c); `false` for every other morph. **`morphs[].user_added`** (new, same
correction): `true` only for a morph in a named-sandbox run whose allomorph has no `ID` at all (a
user hand-edit, FR-050's exception to rule a); `false` otherwise, including for every morph in a
project-cache-sourced run (a project-cache config can never contain a user-added morph).

Two further additive details (T047):
- **`analyses` is a list only for `parsed` and `not_parsed`.** For `invalid_segment`,
  `not_expressible`, `error_no_output` and `not_reached` it is `null`, with `analysis_count: 0`.
  CP3's `HostCounters` reads `analyses: []` as a zero-parse word, so a word hc produced nothing
  for must not carry an empty list (FR-018).
- **`parse_time_ms`** (CP3's existing key): for a sandbox-worker line this is the worker's own
  measured `ParseWord` wall-clock time (`contracts/sandbox-worker.md` section 4), replacing hc's
  printed `Parse time: <n>ms` line as the source; `null` for an invalid segment, unchanged.

### 6.5 `results.jsonl`: the assertion line (test mode)

```json
{
  "index": 0,
  "wordform": "membaca",
  "parse": {"parsed": true, "analysis_count": 2, "outcome": "parsed", "analyses": [ ... ]},
  "assertion": {
    "classification": "pass | regression | new_ambiguity | changed | error",
    "label": null,
    "missing": [[{"form": "mem", "gloss": "ACT"}]],
    "unexpected": [],
    "error_reason": null
  }
}
```

- `label` is `"now_parses"` only for an expected-no-parse assertion that now parses (FR-033).
- `error_reason` is one of `invalid_segment`, `not_expressible`, `error_no_output`, `not_reached`,
  `timeout`.
- For test lines, `parse.analyses` holds the **unmatched actual** parses. Those are the only ones
  hc prints on a failure (F-8). On a pass it is `[]`, with `analysis_count` equal to the number of
  expected parses.

### 6.6 Summary additions (response and `parse_status`)

Parse mode reports counts by `outcome`. Test mode reports counts by `classification`, plus a
reconciliation count and `counter_agreement: true | false`. **Revised naming (CP5 re-plan
2026-09-24):** `hc_counters` is retired to `engine_counters` -- the counts being reconciled against
were always the counted-by-the-worker totals conceptually cross-checked against hc's own
`stats -p`/`-t` output; since there is no hc process left to print an independent count, this is
now a **self-consistency check within the worker's own tally** (the worker's per-word classify
loop vs. its own running totals), kept because FR-017's reconciliation discipline (never trust one
counted total without a second, independently-summed one) is still worth having even with a single
source. When they disagree, the `counter_divergences` entry is shown (FR-017). The totals are
reconciled as:

| `engine_counters` field | Must equal |
|---|---|
| `passed` | `pass` |
| `failed` | `regression + new_ambiguity + changed` |
| `error` | the `invalid_segment` errors (never `not_expressible`, which the engine never sees either -- it is decided before dispatch) |

## 7. Health block additions (`parser.sandbox`, `parser.detected`)

These are additive. The status stays two-state (FR-004).

**Revised (CP5 re-plan 2026-09-24), per D7.** Health is a **presence-plus-`FileVersion` read**,
nothing more: it never spawns a process and never loads the engine (`contracts/tools.md` section
6). The `hc` component -- and everything that only made sense for a launched console process
(`starts`, the `runtime_missing` signal, the `dotnet_tools_dir`/`dotnet_tool_list` `source`
vocabulary) -- is retired. It is replaced by `fieldworks_hermitcrab`, a DLL-presence-and-version
component with no `starts` field at all (there is nothing to start at health time). An engine that
is present, at a recognised version, but still fails to **load** is not a health-time finding --
D7 does not load it -- it surfaces only when a sandbox worker actually tries, on that run's first
`parse`, as `parser_job_failed` with `failure: "engine_unavailable"` (`contracts/tools.md` section
4, `contracts/sandbox-worker.md` section 5). There is no skew advisory (`contracts/tools.md`
section 6): one engine, not two versions to compare.

```json
"sandbox": {
  "status": "ready | unavailable",
  "components": [
    {"component": "fieldworks_hermitcrab", "found": true,
     "expected_path": "C:\\Program Files\\SIL\\FieldWorks 9\\SIL.Machine.Morphology.HermitCrab.dll",
     "file_version": "3.8.2.0", "signal": null, "reason": null},
    {"component": "GenerateHCConfig.exe", "found": true, "expected_path": "C:\\Program Files\\SIL\\FieldWorks 9\\GenerateHCConfig.exe",
     "signal": null, "reason": null}
  ],
  "advisories": []
}
"detected": { "...existing five keys...": "",
  "fieldworks_hermitcrab_version": "3.8.2.0", "generate_hc_config_version": "9.3.11.x" }
```

- `status` is `"ready"` only if `fieldworks_hermitcrab.found and generate.found`. Neither component
  is executed by health, so neither has a `starts` field; the load a `starts` check used to stand
  in for is D7's deliberately-deferred first-run check instead (above).
- `signal` takes one of `not_found` or `not_hermitcrab` (a DLL exists at the expected path but is
  not recognisable as the HermitCrab assembly -- a corrupt or mismatched FieldWorks install).
  ~~`timeout`~~ and ~~`runtime_missing`~~ are retired: there is no process launch to time out, and
  the engine runs in-process via pythonnet inside a FieldWorks installation that is, by definition,
  already present on this machine -- there is no separate runtime to be missing the way `hc`'s
  .NET 10 requirement could be.
- The existing `SANDBOX_SIGNAL_*` constants gain `not_hermitcrab` only (not `runtime_missing`,
  retired above), and it stays outside `CLOSED_SIGNALS`.
- `detected.hc_source` is retired (`contracts/tools.md` section 6): there is one place FieldWorks
  installs the engine, so there is no discovery-source vocabulary left to report.

## 8. Detail models (see `contracts/tools.md` section 4 for field order)

- `ParserConfigFailedDetail` is **new**.
- `ParseSandboxRefusedDetail` is **new, pending M-2**.
- `ParserToolMissingDetail`, `ParserTimeoutDetail` and `ParserEngineMismatchDetail` are unchanged.
