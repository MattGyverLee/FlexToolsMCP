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
```

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
  "versions": {"generate_hc_config": "9.3.11.x", "fieldworks_hermitcrab": "3.8.2.0"}
}
```

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
```

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

```json
{
  "mode": "parse | test",
  "config_source": {"kind": "project_cache", "cache_key": "..."} ,
  "config_source_alt": {"kind": "named_sandbox", "name": "tighten-env", "edited": true, "predates_project_grammar": false},
  "corpus": {"name": "...", "assertion_count": 0} ,
  "versions": {"hc_tool": "3.8.x", "fieldworks_hermitcrab": "3.8.2.0", "generate_hc_config": "9.3.11.x", "hcparse": "5.0.0"},
  "version_skew": false,
  "hc_source": "override | path | dotnet_tools_dir | dotnet_tool_list",
  "generation": {"reused_cache": true, "cache_key": "...", "load_error_count": 0, "load_errors": []},
  "copy": {"bytes": 0, "cleanup": "deleted | failed | not_made", "path_if_failed": null},
  "hc": {"exit_code": 0, "timed_out": false, "in_flight_index": null, "duration_ms": 0, "counters": "ok | unavailable_timeout"},
  "truncated_by_limit": false,
  "advisories": ["sandbox_predates_project_grammar", "hc_engine_version_skew", "grammar_load_errors"]
}
```

`config_source` takes one of two shapes: `{"kind": "project_cache", ...}` or
`{"kind": "named_sandbox", ...}`. The snippet shows both only for illustration; a real record holds
exactly one under the single key `config_source`. `corpus` is present only when `mode == "test"`.

**Also on a sandbox run.** The existing `scope_fingerprint` is set with `scope_kind: "words"`
and `engine: "HC"` (R-14). The existing `project_state.staleness` is set on the R-13 verdicts. The
existing `counters` and `counter_divergences` fields are filled from `stats -p` or `stats -t`.

### 6.3 Sandbox files in the run directory

```
<run_id>/sandbox/
  generate-config.log   # copied from the cache entry; on a warm run, prefixed by one line naming the reuse
  hc-script.txt         # the exact script hc read (UTF-8, no BOM)
  dispatch.json         # the script's per-word dispatch (hcparse contract section 4)
  hc-stdout.txt         # hc's console stream, decoded from UTF-16, written as UTF-8, flushed per line
  hc-stderr.txt
  hc-output.txt         # the result blocks only: hc-stdout minus the load banner
  run.json              # the script's hand-off (hcparse contract section 5)
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
        "morphs": [{"form": "mem", "gloss": "ACT"}, {"form": "baca", "gloss": "read"}],
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
keeps both raw lines in `raw`; `morphs` and `rendered_morphs` are then null (FR-019). **`flags`**
may contain `leading_dash_unverified` (R-09).

Two further additive details (T047):
- **`analyses` is a list only for `parsed` and `not_parsed`.** For `invalid_segment`,
  `not_expressible`, `error_no_output` and `not_reached` it is `null`, with `analysis_count: 0`.
  CP3's `HostCounters` reads `analyses: []` as a zero-parse word, so a word hc produced nothing
  for must not carry an empty list (FR-018).
- **`parse_time_ms`** (CP3's existing key) follows `flags`: hc's `Parse time: <n>ms` when it
  printed one, else `null`. hc prints no time line for an invalid segment.

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

Parse mode reports counts by `outcome`. Test mode reports counts by `classification`, plus
`hc_counters: {tests, passed, failed, error}` and `counter_agreement: true | false`. When they
disagree, the `counter_divergences` entry is shown (FR-017). The totals are reconciled as:

| hc counter | Must equal |
|---|---|
| `passed` | `pass` |
| `failed` | `regression + new_ambiguity + changed` |
| `error` | the `invalid_segment` errors (hc never sees not-expressible) |

## 7. Health block additions (`parser.sandbox`, `parser.detected`)

These are additive. The status stays two-state (FR-004).

```json
"sandbox": {
  "status": "ready | unavailable",
  "components": [
    {"component": "hc", "found": true, "expected_path": "C:\\Users\\u\\.dotnet\\tools\\hc.exe",
     "starts": false, "signal": "runtime_missing", "source": "dotnet_tools_dir",
     "reason": "hc needs the .NET runtime Microsoft.NETCore.App 10.0, which is not installed"},
    {"component": "GenerateHCConfig.exe", "found": true, "expected_path": "C:\\Program Files\\SIL\\FieldWorks 9\\GenerateHCConfig.exe",
     "starts": null, "signal": null, "source": "fieldworks_dir", "reason": null}
  ],
  "advisories": ["hc_engine_version_skew"]
}
"detected": { "...existing five keys...": "",
  "fieldworks_hermitcrab_version": "3.8.2.0", "generate_hc_config_version": "9.3.11.x", "hc_source": "dotnet_tools_dir" }
```

- `status` is `"ready"` only if `hc.found and hc.starts and generate.found`. `GenerateHCConfig` is
  not executed by health, so its `starts` is `null`.
- `signal` takes one of `not_found`, `timeout`, `runtime_missing` or `not_hermitcrab`.
- The existing `SANDBOX_SIGNAL_*` constants gain `runtime_missing` and `not_hermitcrab`, and stay
  outside `CLOSED_SIGNALS`.

## 8. Detail models (see `contracts/tools.md` section 4 for field order)

- `ParserConfigFailedDetail` is **new**.
- `ParseSandboxRefusedDetail` is **new, pending M-2**.
- `ParserToolMissingDetail`, `ParserTimeoutDetail` and `ParserEngineMismatchDetail` are unchanged.
