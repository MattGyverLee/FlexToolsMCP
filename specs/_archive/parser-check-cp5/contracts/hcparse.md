# Contract: `hcparse.ps1`, the interface between the MCP and the script

**Retired (CP5 re-plan 2026-09-24): Parse and Test modes.** See `HANDOFF.md` and
`reviews/research-cycle1-domain.md` for the decision record. The sandbox no longer shells out to
an `hc` console tool to parse or test words: FieldWorks does not ship one, and the maintainer
chose not to package a stand-in (`reference/hc_fw_prototype.py`, rejected). Parse and Test now run
**in-process**, in a `--sandbox` mode of the parse worker (`server/parse/worker_main.py`), which
loads the FieldWorks HermitCrab engine directly via pythonnet and calls it (see
`contracts/sandbox-worker.md`, new in CP5). Every Parse/Test-specific piece of this contract below
-- `-HcPath`, `dispatch.json`, the word-quoting and leading-dash rules, exit codes 5 and 6, and the
Parse/Test rows of sections 2, 3, 6 and 7 -- is retired along with them, kept here only as a record
of what the old spine did. **This file now governs Generate mode only.** Generate mode (the
allowlisted project copy, `GenerateHCConfig.exe`, and the config cache in `sandbox/cache.py`) is
unchanged by CP5.

**As implemented (T107):** the script's Parse and Test code is deleted, not just unused.
`-Mode Parse` and `-Mode Test` are refused with exit 2 before anything is written, and their
parameters (`-HcPath`, `-Config`, `-WordFile`, `-Words`, `-AssertionFile`, `-TimeoutSeconds`) are
gone from `param()`. `HCPARSE_VERSION` is `6.0.0`.

An `HCPARSE_VERSION` bump still invalidates the config cache: because `key.json`'s cache key
folds in `hcparse_version` (data-model.md section 3), bumping the constant regenerates every cache
entry exactly once, the next time each is used, rather than needing an explicit prune.

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
| `-Mode` | all | `Generate` \| ~~`Parse`~~ \| ~~`Test`~~ -- **Retired (CP5 re-plan 2026-09-24):** the script is invoked only as `-Mode Generate` now |
| ~~`-HcPath`~~ | ~~Parse, Test~~ | **Retired (CP5 re-plan 2026-09-24).** There is no `hc` process to point at; see `contracts/sandbox-worker.md` |
| `-GenerateHCConfigPath` | Generate | Required. **Never hard-coded** (FR-002) |
| `-FwData` | Generate | Absolute path to the live `.fwdata`. It is only read |
| `-WorkDir` | Generate | Created by the MCP, and holds the marker. The script copies the allowlist into it (`<WorkDir>/<name>/<name>.fwdata` and `<WorkDir>/<name>/WritingSystemStore/**`) and deletes everything it put there in `finally`. The marker `.flextoolsmcp-sandbox-work` is left for the MCP, which removes `work/<run_id>/` itself |
| **`-ConfigOut`** | Generate | The output config path. **Refused** (exit 3) if it resolves under a `sandboxes` directory of the sandbox root (FR-026) |
| ~~`-Config`~~ | ~~Parse, Test~~ | **Retired (CP5 re-plan 2026-09-24).** The sandbox worker takes the config path directly (`--config`, `contracts/sandbox-worker.md`) |
| ~~`-WordFile`~~ | ~~Parse~~ | **Retired (CP5 re-plan 2026-09-24).** Words now travel as `parse` messages to the sandbox worker |
| ~~`-Words`~~ | ~~Parse~~ | **Retired (CP5 re-plan 2026-09-24)** |
| ~~`-AssertionFile`~~ | ~~Test~~ | **Retired (CP5 re-plan 2026-09-24).** The corpus JSON (data-model section 5) is still the shape; it is now read by the sandbox client, not by this script |
| `-RunDir` | Generate | The destination for this invocation's files: the cache entry's `.partial/`. (Parse and Test used to write their own `sandbox/` here; that use is retired) |
| ~~`-TimeoutSeconds`~~ | ~~Parse, Test~~ | **Retired (CP5 re-plan 2026-09-24).** The wall clock is now the `SandboxClient` watchdog around the worker process (`contracts/sandbox-worker.md`) |
| `-GenerateTimeoutSeconds` | Generate | Default 600. Covers the unverified SLDR start-up (spec Assumptions) |

The script declares **`$script:HCPARSE_VERSION = '<semver>'`** on its own line near the top
(FR-024). Python reads it with the regex `^\$script:HCPARSE_VERSION\s*=\s*'([^']+)'`, and a test
pins that exactly one match exists.

## 3. Exit codes (the script's own, not hc's)

| Code | Meaning |
|---|---|
| 0 | The invocation completed. **The outcome is in `run.json`**, and a 0 does not mean the words parsed |
| 1 | An unexpected script error (not a designed outcome). `run.json` is still written, with `error` set, when the invocation got past parameter validation |
| 2 | A bad parameter or a missing input file |
| 3 | `-ConfigOut` was refused (it was under the sandboxes root) |
| 4 | Generation failed (details in `run.json`) |
| ~~5~~ | ~~hc failed to start (`Load Error` / `IO Error`, exit -1)~~ -- **Retired (CP5 re-plan 2026-09-24).** An unloadable engine is now `parser_job_failed` (`failure: "engine_unavailable"`) from the sandbox worker, not an hcparse exit code; see `contracts/sandbox-worker.md` |
| ~~6~~ | ~~Timeout (hc or the generator was killed)~~ -- **Retired for the parse/test half.** A generator timeout is still 6; a parse timeout is now the `SandboxClient` watchdog, reported as `parser_timeout` |

Codes 2 and 3 are decided during parameter validation, before anything is written: no
`run.json`, no copy, and no tool is started. In Generate mode, 0 requires all three of R-05's
conditions (generator exit 0, a non-empty config, a `Writing completed.` line); anything else is 4.
**Retired:** the sentence "In Parse and Test modes, hc exit -1 is 5" no longer applies -- those
modes do not run through this script (CP5 re-plan 2026-09-24).

Python reads `run.json` first and uses the exit code only as a cross-check. A missing `run.json`,
because the script was killed, is handled from the flushed files (research R-06).

## 4. `dispatch.json`: written before hc starts (Parse, Test)

**Retired in full (CP5 re-plan 2026-09-24).** There is no `hc` script line, no word-quoting rule
and no `leading_dash_unverified` flag left to build: the sandbox worker takes a wordform directly
in a `parse` message and returns a structured result, so nothing here is transliterated into a
command language. `contracts/sandbox-worker.md` describes the replacement per-word request/result
shape. The rest of this section is kept verbatim below as the historical record of the retired
`hc`-script dispatch, including the quoting and reason-code rules it enforced.

```json
{
  "schema": "flextoolsmcp.hc-dispatch/1",
  "mode": "parse",
  "items": [
    {"index": 0, "word": "don't", "sent": true, "line": "parse \"don't\"", "reason": null, "flags": []},
    {"index": 1, "word": "a\"b'c", "sent": false, "line": null, "reason": "both_quote_characters", "flags": []},
    {"index": 2, "word": "-an", "sent": true, "line": "parse \"-an\"", "reason": null, "flags": ["leading_dash_unverified"]}
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

Each item has exactly these keys. `index` is the 0-based input position, counting unsent items.
A sent item has `reason: null`; an unsent one has `line: null`. **`flags`** is always a list; the
only flag is `leading_dash_unverified`, set on a sent word beginning with `-` until LIVE L-2
settles it (research R-09). In Parse mode a blank `-WordFile` line is an item with reason `empty`,
and a word containing a tab, CR or LF is `control_character`.

The item order is the order of `-WordFile` or `-AssertionFile`, which Python already ordered
(FR-015). Words are never reordered or de-duplicated here.

**Test mode** (`mode: "test"`) has one item per corpus assertion, with the same keys. The word is
checked and quoted exactly as in Parse mode, and those word faults are checked first. A sent line
is `test -p <f:g|f:g> [-p ...] [--] <quoted word>`:
- there is one `-p` per expected parse, in corpus order, and its morphs are joined by `|`;
- every morph is `form:gloss` (F-5). An empty gloss is written `?` (F-7), and an empty form is
  allowed (`:ZERO`);
- `--` comes only before a word beginning with `-`, which is also flagged
  `leading_dash_unverified` (L-2);
- `expected: []` becomes `test <quoted word>` with no `-p`. hc's `TestCommand` then has no
  expected parses, so it prints `Test passed.` only when the word has no parse. Otherwise it prints
  `Test failed.`, with `Expected parses:` / `None` and the extras under `Actual parses:`.

An assertion is not sent when a form or gloss contains `|`, `:` or `\`
(`delimiter_in_expectation`), or `'`, `"` or whitespace (`quote_or_space_in_expectation`), or
when an expected parse has zero morphs (`empty_expected_parse`). The first fault found wins. The
hc script therefore never contains a backslash: in `TestCommand.Split`, a `\` before a delimiter
after the first position loops forever. It also never contains a morph without `:`, which would
throw outside the `try` and leak the `-p` list into the next test (F-5).

The script checks `-AssertionFile` structurally during parameter validation. Unreadable JSON, a
`schema` other than `flextoolsmcp.hc-corpus/1`, a missing `assertions` list, or an assertion
without a string `word`, a list `expected`, list parses and string `form`/`gloss` is exit 2, and
nothing is written.

## 5. `run.json`: written at the end of every invocation that reaches `finally`

```json
{
  "schema": "flextoolsmcp.hcparse-run/1",
  "hcparse_version": "5.0.0",
  "mode": "parse",
  "exit_code": 0,
  "inputs": {"config": "...", "word_count": 3, "timeout_seconds": 600},
  "started_at": "<iso8601Z>", "ended_at": "<iso8601Z>", "duration_ms": 0,
  "generate": {"exit_code": 0, "timed_out": false, "config_bytes": 0, "writing_completed": true},
  "hc": {"exit_code": 0, "timed_out": false, "killed": false, "in_flight_index": null, "stdout_bom": false},
  "copy": {"bytes": 0, "deleted": true},
  "items": "<the dispatch.json items, repeated for a self-contained hand-off>",
  "error": "<optional: the message that ended the invocation>"
}
```

- `generate` and `copy` are present only in Generate mode; `hc` and `items` only in Parse and Test
  modes.
- `exit_code` is the script's own exit code (section 3), the same value the process exits with.
- `error` is present only when the invocation ended with an error (exit 1, 4, 5 or 6): the ASCII
  message the script also printed. It is for humans; Python branches on the codes and sections.
- Generate `inputs` are `{fwdata, config_out, timeout_seconds}`. `generate.exit_code` is null on a
  timeout or when the generator never started; `copy.bytes` is the sum of the copied allowlist.
- `hc.exit_code` is null on a timeout. `hc.in_flight_index` is the dispatch `index` of the word
  whose header had no terminating blank line at the kill, else null. `hc.stdout_bom` is true when
  hc's stdout began with a UTF-16 BOM (which is stripped from `hc-stdout.txt`).
- Python folds `run.json` into `meta.sandbox` (data-model 6.2) and never scrapes console prose.

## 6. Files the script writes into `-RunDir`

**Live rows (Generate mode, unchanged by CP5):**

| File | Mode | Encoding |
|---|---|---|
| `generate-config.log` | Generate | UTF-8, the generator's stdout and stderr verbatim (FR-009) |
| `run.json` | all | UTF-8 |

**Retired rows (CP5 re-plan 2026-09-24) -- Parse and Test wrote these; the sandbox worker writes
no equivalent files of its own (its result travels back over stdout as JSON; the run record's
`sandbox/` files for a worker-backed run are described in `data-model.md` section 6.3, revised
for CP5):**

| File | Mode | Encoding |
|---|---|---|
| ~~`hc-script.txt`~~ | ~~Parse, Test~~ | UTF-8, **no BOM** (H11 verbatim): `[IO.File]::WriteAllLines(p, lines, (New-Object Text.UTF8Encoding($false)))` |
| ~~`dispatch.json`~~ | ~~Parse, Test~~ | UTF-8 |
| ~~`hc-stdout.txt`~~ | ~~Parse, Test~~ | UTF-8, no BOM. Decoded from hc's **UTF-16LE** stdout (research F-1). `AutoFlush` is on, one line per write |
| ~~`hc-stderr.txt`~~ | ~~Parse, Test~~ | UTF-8 |

**The hc script (retired, historical record only).** It had one command per sent item. It ended
with `stats -p` in Parse mode or `stats -t` in Test mode. It never contained `tracing on`, because
CP5 has no trace. `hc` was invoked as `-i <Config> -s <hc-script.txt>`. It was **never** given
`-o` (research F-4) or `-c` (spec Assumptions: hc runs without continue-on-error).

## 7. Invariants tested against the script (Windows, with fake hc and fake generator)

**Live (Generate mode):**

- The copy holds only allowlisted files. No `*.lock`, `.hg` or `LinkedFiles` appears in
  `-WorkDir` at any point. This is checked by a fake generator that lists its folder.
- `-WorkDir` is empty after the invocation, on success, generator failure, or timeout.
- `-ConfigOut` under `sandboxes` exits 3, and no file is written.
- Console output is ASCII (checked over the captured stdout).
- `HCPARSE_VERSION` is present exactly once.

**Retired (CP5 re-plan 2026-09-24) -- these invariants belonged to the Parse/Test `hc` spine and
have no equivalent hcparse.ps1 invariant now; the corresponding isolation and encoding invariants
for the sandbox worker are in `contracts/sandbox-worker.md`:**

- ~~`-WorkDir` is empty after the invocation on hc start failure~~ (there is no hc start to fail).
- ~~A word containing `'` is emitted double-quoted. A word containing `"` is emitted
  single-quoted. A word containing both is `sent: false`~~ (no command language is built).
- ~~Non-Latin words round-trip byte-exactly: the fake hc echoes its script back in UTF-16LE, and
  the script's `hc-stdout.txt` matches the input in UTF-8~~ (no UTF-16LE stdout stream; the worker
  channel is UTF-8 JSON, `worker_main.py`'s `_force_utf8_stdio`).
- ~~On timeout, `hc-stdout.txt` holds every line the fake emitted before the kill, and `run.json`
  names `in_flight_index`~~ (timeout handling moved to the `SandboxClient` watchdog).
