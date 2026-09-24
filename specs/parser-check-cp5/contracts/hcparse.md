# Contract: `hcparse.ps1`, the interface between the MCP and the script

The packaged script is `src/flextoolsmcp/scripts/hcparse.ps1` (parent section 5.3). It replaces
the root-level contributed copy, which is deleted but remains in git history.

It targets **Windows PowerShell 5.1**. It uses no PowerShell 7 syntax: no `??`, no `?.`, no
ternary, no `&&`.

## 1. Invocation (FR-022)

```
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <hcparse.ps1> <params>
```

- The MCP builds this as an **argv list**, never as a command string and never through string
  evaluation.
- stdin is closed.
- The script's own console output is **ASCII only** (FR-021). It is progress prose for a human, and
  the MCP never parses it (FR-023).

## 2. Parameters

| Parameter | Mode | Notes |
|---|---|---|
| `-Mode` | all | `Generate` \| `Parse` \| `Test` |
| `-HcPath` | Parse, Test | Required. An `hc.exe`, or an `hc.dll` run as `dotnet <dll>` (research R-03). **Never hard-coded** (FR-002) |
| `-GenerateHCConfigPath` | Generate | Required. **Never hard-coded** (FR-002) |
| `-FwData` | Generate | Absolute path to the live `.fwdata`. It is only read |
| `-WorkDir` | Generate | Created by the MCP, and holds the marker. The script copies the allowlist into it and deletes its contents in `finally` |
| **`-ConfigOut`** | Generate | The output config path. **Refused** (exit 3) if it resolves under a `sandboxes` directory of the sandbox root (FR-026) |
| `-Config` | Parse, Test | The config to run: a cache entry's or a sandbox's `hc-config.xml` |
| `-WordFile` | Parse | UTF-8, one word per line. Read with `Get-Content -Encoding UTF8` (H11, verbatim) |
| `-Words` | Parse | For stand-alone use. Split on `[,\s]+` (H11, verbatim) |
| `-AssertionFile` | Test | The corpus JSON (data-model section 5) |
| `-RunDir` | all | The destination for this invocation's files. Parse and Test use the run's `sandbox/`; Generate uses the cache entry's `.partial/` |
| **`-TimeoutSeconds`** | Parse, Test | The wall clock for the `hc` process (FR-020) |
| `-GenerateTimeoutSeconds` | Generate | Default 600. Covers the unverified SLDR start-up (spec Assumptions) |

The script declares **`$script:HCPARSE_VERSION = '<semver>'`** on its own line near the top
(FR-024). Python reads it with the regex `^\$script:HCPARSE_VERSION\s*=\s*'([^']+)'`, and a test
pins that exactly one match exists.

## 3. Exit codes (the script's own, not hc's)

| Code | Meaning |
|---|---|
| 0 | The invocation completed. **The outcome is in `run.json`**, and a 0 does not mean the words parsed |
| 2 | A bad parameter or a missing input file |
| 3 | `-ConfigOut` was refused (it was under the sandboxes root) |
| 4 | Generation failed (details in `run.json`) |
| 5 | hc failed to start (`Load Error` / `IO Error`, exit -1) |
| 6 | Timeout (hc or the generator was killed) |

Python reads `run.json` first and uses the exit code only as a cross-check. A missing `run.json`,
because the script was killed, is handled from the flushed files (research R-06).

## 4. `dispatch.json`: written before hc starts (Parse, Test)

```json
{
  "schema": "flextoolsmcp.hc-dispatch/1",
  "mode": "parse",
  "items": [
    {"index": 0, "word": "don't", "sent": true, "line": "parse \"don't\"", "reason": null},
    {"index": 1, "word": "a\"b'c", "sent": false, "line": null, "reason": "both_quote_characters"}
  ]
}
```

`reason` is a closed enum:
- `both_quote_characters`
- `empty`
- `control_character`
- `delimiter_in_expectation` (FR-027)
- `quote_or_space_in_expectation`
- `empty_expected_parse`

The item order is the order of `-WordFile` or `-AssertionFile`, which Python already ordered
(FR-015). Words are never reordered or de-duplicated here.

## 5. `run.json`: written at the end of every invocation that reaches `finally`

```json
{
  "schema": "flextoolsmcp.hcparse-run/1",
  "hcparse_version": "5.0.0",
  "mode": "parse",
  "inputs": {"config": "...", "word_count": 3, "timeout_seconds": 600},
  "started_at": "<iso8601Z>", "ended_at": "<iso8601Z>", "duration_ms": 0,
  "generate": {"exit_code": 0, "timed_out": false, "config_bytes": 0, "writing_completed": true},
  "hc": {"exit_code": 0, "timed_out": false, "killed": false, "in_flight_index": null, "stdout_bom": false},
  "copy": {"bytes": 0, "deleted": true},
  "items": "<the dispatch.json items, repeated for a self-contained hand-off>"
}
```

- `generate` is present only in Generate mode, and `hc` only in Parse and Test modes.
- Python folds `run.json` into `meta.sandbox` (data-model 6.2) and never scrapes console prose.

## 6. Files the script writes into `-RunDir`

| File | Mode | Encoding |
|---|---|---|
| `generate-config.log` | Generate | UTF-8, the generator's stdout and stderr verbatim (FR-009) |
| `hc-script.txt` | Parse, Test | UTF-8, **no BOM** (H11 verbatim): `[IO.File]::WriteAllLines(p, lines, (New-Object Text.UTF8Encoding($false)))` |
| `dispatch.json` | Parse, Test | UTF-8 |
| `hc-stdout.txt` | Parse, Test | UTF-8, no BOM. Decoded from hc's **UTF-16LE** stdout (research F-1). `AutoFlush` is on, one line per write |
| `hc-stderr.txt` | Parse, Test | UTF-8 |
| `run.json` | all | UTF-8 |

**The hc script.** It has one command per sent item. It ends with `stats -p` in Parse mode or
`stats -t` in Test mode. It never contains `tracing on`, because CP5 has no trace. `hc` is invoked
as `-i <Config> -s <hc-script.txt>`. It is **never** given `-o` (research F-4) or `-c` (spec
Assumptions: hc runs without continue-on-error).

## 7. Invariants tested against the script (Windows, with fake hc and fake generator)

- The copy holds only allowlisted files. No `*.lock`, `.hg` or `LinkedFiles` appears in
  `-WorkDir` at any point. This is checked by a fake generator that lists its folder.
- `-WorkDir` is empty after the invocation, on success, generator failure, timeout, and hc start
  failure.
- `-ConfigOut` under `sandboxes` exits 3, and no file is written.
- A word containing `'` is emitted double-quoted. A word containing `"` is emitted single-quoted.
  A word containing both is `sent: false`.
- Non-Latin words round-trip byte-exactly: the fake hc echoes its script back in UTF-16LE, and the
  script's `hc-stdout.txt` matches the input in UTF-8.
- On timeout, `hc-stdout.txt` holds every line the fake emitted before the kill, and `run.json`
  names `in_flight_index`.
- Console output is ASCII (checked over the captured stdout).
- `HCPARSE_VERSION` is present exactly once.
