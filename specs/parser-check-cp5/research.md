# Research: parser-check CP5 -- the sandbox spine

**Date**: 2026-09-24. **Base**: `main` at `2772b52`.

**Method**: four read-only source sweeps, each covering an independent area:
- health and discovery;
- the run record and job model;
- the tool surface and contract;
- the `hc` and `GenerateHCConfig` sources at `C:\Github\machine` `b77b2337` and `C:\Github\FieldWorks` `e1434c8`.

Load-bearing claims were then spot-checked by hand. Anything that source cannot settle is marked
**[LIVE]** and assigned to a live question in `quickstart.md`.

This file records decisions. The requirement text stays in `spec.md`.

---

## Source facts the design rests on

These come on top of the six facts in the spec's Summary. Each one changes code.

| # | Fact | Evidence | Consequence |
|---|---|---|---|
| F-1 | `hc` sets `Console.OutputEncoding = Encoding.Unicode`, so its piped stdout is **UTF-16LE**, not UTF-8 | `Program.cs:14-15` (checked by hand) | The script must decode hc's stdout as UTF-16. Decoding it as UTF-8 or ANSI is section 4's mojibake bug, one layer down. **[LIVE L-3]**: is a BOM emitted? |
| F-2 | Without `-s`, `hc -i x` goes interactive and blocks on `Console.ReadLine()`. With no `-i`, `-h` or no args, it prints usage and exits -1 without reading stdin | `Program.cs:98-113, 37-51` | The identity probe is `hc -h` with stdin closed. A run always passes `-s` |
| F-3 | The usage text starts `Usage: hc [OPTIONS]` / `HermitCrab.NET is a phonological and morphological parser.` `hc` has no version option | `Program.cs:164-167` | Identity is recognised from those two lines. The version comes from somewhere else (R-03) |
| F-4 | The `-o` writer is `new StreamWriter(file)`: UTF-8, AutoFlush off, flushed only on `Close()`. The console writer flushes on every write | `Program.cs:58` | Never pass `-o`. The script reads the console stream line by line and writes it to a file it flushes (R-06) |
| F-5 | `test` parses `-p` values outside its `try`. A morph without `:` throws, the `finally` never runs, and `_expectedParses` **leaks into the next `test`** | `TestCommand.cs:31, 107` | Every emitted morph is `form:gloss`, with no exceptions. FR-027's check also rejects an assertion with an empty morph list |
| F-6 | `WriteParse` pads each column to `max(len(form), len(gloss))`, as .NET `string.Length`, i.e. **UTF-16 code units**, and joins columns with a single space. An empty gloss prints as `?` (`MorphInfo.cs:25-26`) | `Extensions.cs:274-304` | Column recovery must count UTF-16 units, not Python code points. Otherwise an astral-plane character misaligns every later column (R-08) |
| F-7 | `MorphInfo.Equals` compares form and gloss, where the gloss is already `?`-substituted | `MorphInfo.cs:39-41` | A seeded expectation `form:?` round-trips exactly (R-10) |
| F-8 | On failure `test` prints only the **unmatched** expected parses and the **unmatched** actual parses, or `None` | `TestCommand.cs` | Missing is the Expected section being non-`None`. Unexpected is the Actual section being non-`None`. FR-031 maps onto that directly |
| F-9 | `GenerateHCConfig`'s `ConsoleLogger` writes **one line per grammar error**, in seven fixed templates plus bare-reason and UI-callback lines, interleaved with four fixed progress lines | `ConsoleLogger.cs` | A load error is any line that is not one of the known progress lines (R-05) |
| F-10 | `ConsoleLogger.UnmatchedReduplicationIndexedClass` throws `NotImplementedException`, so one ill-formed reduplication index crashes the generator | `ConsoleLogger.cs:204-207` | A crash has no `Writing completed.` line, so it becomes `parser_config_failed`. The hint names the static grammar scan |
| F-11 | `check_active_parser` reads `ActiveParser` through LCM, and its only caller is the worker, which **opens the project** | `parser_probe.py:788`, `worker_main.py:911-938` | FR-036 needs a new path that does not open LCM (R-02) |
| F-12 | `RunRecord.read_meta` **silently drops** any key that is not a `RunMeta` field, and every stage change rewrites the meta | `record.py:513-514` | `spine` and `sandbox` must be declared `RunMeta` fields, the way CP4 declared `filing`. A bare dict key would vanish at the first stage change |
| F-13 | `WorkerPool` keys workers by `(project, role)` | `worker_client.py:827-870` | Two concurrent sandbox jobs on one project would share a pooled client. The sandbox client is built **per run**, outside the pool (R-07) |
| F-14 | `parser_timeout` and `parser_tool_missing` have detail models but **no emitter anywhere** | `response_models.py:439, 626`; grep | CP5 is their first emitter. Their golden fixtures exist already, so nothing about the shape changes |
| F-15 | CP1's boundary tests forbid any argv containing `hc`, and the dynamic test fakes `subprocess.run` with empty stdout | `tests/test_cp1_boundary.py:234, 814, 826, 1403` | FR-003, which *runs* hc, collides with a standing CP1 invariant (R-04) |
| F-16 | `diff.shared_mode_active` covers `open_shared` and `open_exclusive`, **not `held_by_other`** | `diff.py:74, 130` | FR-040 names "held by another program". R-13 decides how that is handled |
| F-17 | USAGE.md has no row for `flextools_parse_cancel` (drift from CP4) | grep | Fixed in the same change as the sandbox row |

---

## R-01 -- What the script owns and what Python owns

**Decision.** The script, `hcparse.ps1`, is the **mechanism**. It does these things and nothing else:
- makes the minimal copy into a work directory the MCP names;
- runs `GenerateHCConfig` with its output captured;
- turns a word list or assertion file into an `hc` script (quoting, and the not-expressible check);
- runs `hc` under a timeout, streaming its decoded console output to a flushed UTF-8 file;
- kills the process tree on timeout;
- writes `dispatch.json` before `hc` starts and `run.json` at the end;
- deletes the copy in `finally`.

Python is the **policy**. It owns:
- discovery;
- the engine check;
- the free-space check;
- the cache (key, lock, prune, invalidation);
- sandbox and corpus files;
- word-list ordering (dedup, NFC, limit);
- the single parser of hc's output;
- classification;
- the run record.

The script is invoked twice per cold job, in two modes:
- `-Mode Generate` writes to the cache entry, under the cache-key lock;
- `-Mode Parse` or `-Mode Test` writes to the run.

A warm job invokes it once.

**Rationale.**
- Principle VI: each rule has exactly one owner. Quoting lives only in the script, next to the H11
  encoding lessons, which FR-014 says to keep verbatim in the script. Output parsing lives only in
  Python, where it is unit-testable and where the job runner needs it per word as results arrive.
- Two modes let the cache lock cover generation only. A single invocation would hold the lock for
  the whole parse, so a second job on the same grammar would wait hours for a config that was ready
  in seconds.

**Reading FR-023 ("per-word results").** `run.json`'s per-word entries record what the script
*did* with each word:
- `sent`, or `not_expressible` with the reason;
- the hc script line;
- the in-flight index on timeout.

The *interpretation* of hc's output (analyses, outcome) is Python's. That output is folded into the
run record from the flushed `hc-stdout.txt`, never from console prose the script prints. Two
parsers of one format would be Principle VI's divergence risk. **Flagged at the plan gate**: if
the maintainer reads FR-023 as "the script classifies", this moves, and the cost is a second parser.

**Alternatives considered.**
- *Python does everything and the script is dropped.* Rejected: FR-022 requires the script. The
  maintainer also runs it by hand, and it stays usable stand-alone.
- *The script parses and classifies.* Rejected: this needs a second parser, or loses per-word
  streaming. PowerShell 5.1 unit tests would also need Pester, which this repository does not use.

## R-02 -- The engine check without opening the project (FR-036)

**Decision.** Stream-read the **live** `.fwdata` as a file: read-only, `FileShare.ReadWrite`, and
no LCM. `ElementTree.iterparse` stops at the first `rt` element with `class="MoMorphData"`. From
it, take the `ParserParameters` text, and parse that inner XML through the existing
`parse/measure.py:summarize_parser_parameters`. The result is cached in the cache entry's `key.json`
under the same `(path, size, mtime_ns)`, so a warm job never re-scans the file. The check fails
safe:
- absent, unparseable, or a read error that persists after one retry counts as XAmple, which
  gives `parser_engine_mismatch`;
- the refusal's hint says the value could not be read, so a mid-save read is distinguishable.

**Rationale.** FR-036 says the check runs **before** any copy. The spec's Assumptions bullet ("the
engine check reads the copy") contradicts it, and the FR wins. A plain file read takes no
`.fwdata.lock`, so it does not trip memory note `non-shared-projects-single-opener`. It also works
while FLEx holds the project **[LIVE L-7]**. `check_active_parser` stays exactly as it is for the
in-process spines.

**Spec correction.** The Assumptions bullet is amended to say "reads the live file as a stream,
before the copy; never through LCM" (task in Phase 7).

**Alternatives considered.**
- *Read it from the copy.* Rejected: it breaks FR-036's order, and a refusal would then come after a
  multi-hundred-MB copy.
- *`check_active_parser` via the worker.* Rejected: it opens the project, and that takes the lock on
  a non-shared project.

**When the check runs.** It runs when a job would **generate** a config (the project cache source)
and when a sandbox is **created**. A run against an existing named sandbox skips it. That config
is HermitCrab XML by construction, and its staleness advisory (FR-029) needs only a `stat`.

## R-03 -- Discovery order, identity, "cannot start", and versions (FR-001..FR-005)

**Decision.** `discover_hc_tool` gains a recorded `source` and the four-step order of FR-001:
1. The `HC_TOOL_PATH` override. As today, a missing path is final and does not fall through.
2. `shutil.which("hc")`.
3. `%USERPROFILE%\.dotnet\tools\hc.exe`, checked directly.
4. `dotnet tool list -g`, with the existing 5 s bound. It runs only when steps 1-3 miss.

A hit is accepted in two forms:
- an `hc.exe` shim;
- an `hc.dll`, which is invoked as `dotnet hc.dll`. This is the form the maintainer's original
  script used, and the one R-15's no-SDK route produces.

Identity and startability come from **one bounded execution**, `hc -h`, with stdin closed and a 5 s
timeout. It is classified from stdout decoded as UTF-16LE and stderr decoded as UTF-8:

| Observation | Result |
|---|---|
| Stdout contains both usage lines (F-3) | `found=True, starts=True` |
| .NET host failure: stderr mentions a missing framework, or the process exits `0x80008096` / `0x8000809A` **[LIVE L-5]**. The `Framework: 'Microsoft.NETCore.App', version 'X'` line is parsed | `found=True, starts=False, signal="runtime_missing"`, with a reason naming the runtime and version |
| Anything else | `found=False, signal="not_hermitcrab"` |
| Timeout | `found=True, starts=False, signal="timeout"` |

The probe result is memoised for the life of the process, keyed on `(path, size, mtime_ns)`.

**Versions (FR-005)**, all read from file metadata, never compared to a floor:
- **hc tool**: from the tool store path `.dotnet\tools\.store\sil.machine.morphology.hermitcrab.tool\<version>\`,
  or from the `dotnet tool list` row. For a `.dll` hit, from the `FileVersion` of
  `SIL.Machine.Morphology.HermitCrab.dll` beside it.
- **FieldWorks' bundled HermitCrab**: the `FileVersion` of
  `<fw>\SIL.Machine.Morphology.HermitCrab.dll`, where `<fw>` comes from
  `versioning.get_resolved_fieldworks_dir()`.
- **GenerateHCConfig**: its `FileVersion`.

Version skew is a warning, `hc_engine_version_skew`, comparing the tool's HermitCrab version with
FieldWorks'. It never refuses (Q3 default). `FileVersion` is read through the Win32
`GetFileVersionInfoW` call via `ctypes`. It needs no pythonnet and no assembly load, so health
stays cheap.

**Rationale.**
- Step 3 is the edge case of US1 scenario 2: a server started before the tool was installed.
- Running `hc -h` is the only way to tell "not HermitCrab" and "cannot start" apart. FR-003 and
  FR-004 both require that.
- `dotnet tool list` needs an SDK. On an SDK-less machine it fails, and step 3 already found the
  file, so that failure never reads as "not installed" (Edge Cases).

**Alternatives considered.**
- *Parse `hc.runtimeconfig.json` to predict startability.* Rejected: it predicts without observing,
  and it misses a corrupt install.
- *Load the dll through pythonnet for its version.* Rejected: heavy, and health must stay light.

## R-04 -- The CP1 boundary invariant and FR-003

**Decision.** CP1's "never shells out to the parser" invariant is **narrowed**, not dropped:
- `tests/test_cp1_boundary.py` gains exactly one permitted argv shape: `[<hc>, "-h"]`, or
  `[dotnet, <hc.dll>, "-h"]`.
- A new pinned test asserts that discovery never passes `-i`, `-s` or `-o`, and never runs
  `GenerateHCConfig`.
- The dynamic test's fake `subprocess.run` gets a usage-text stdout for the `-h` shape.

**Rationale.** CP1's point is that health loads no grammar and parses nothing. `hc -h` exits
before any `-i` is read (F-2). The invariant's meaning survives, and only its letter needs one
exception. That exception is tested, so it cannot widen silently.

**Alternative.** *Keep discovery file-only and move the startability probe into the sandbox tool.*
Rejected: FR-004 puts "cannot start" in **health**, and US1 is the P1 story that delivers it.

## R-05 -- Judging generation (FR-009, FR-010)

**Decision.** Generation succeeds only when **all** of these hold:
- exit code 0;
- the config file exists and is non-empty;
- the captured output contains the line `Writing completed.`

Anything else is `parser_config_failed` (`exit_code`, `stderr_tail`, `log_path`, `run_id`). Case
by case:
- exit 0 with the help text, which happens with fewer than two arguments, fails because there is no
  `Writing completed.`;
- the locked (exit 1) and older-version (exit 1) failures carry their verbatim messages in
  `stderr_tail`;
- a crash (F-10) or an unknown non-zero exit fails the same way;
- a timeout is also `parser_config_failed`, with `exit_code: null` and a hint saying so. Generation
  is not a parse, so `parser_timeout`, which counts words, does not fit.

**Load errors.** A load error is every output line that is **not** one of:
- `Loading FieldWorks project...`
- `Loading completed.`
- `Writing HC configuration file...`
- `Writing completed.`

Each one is kept verbatim and tagged with the template it matches (`undefined_phoneme`,
`invalid_affix_process`, `phoneme_no_grapheme`, `duplicate_grapheme`, `invalid_environment`,
`invalid_reduplication_form`, `invalid_rewrite_rule`, or `other`). The count and the list go into
the cache entry's `key.json`, and every run that uses the entry copies them. That includes warm
runs, because the grammar the run parsed is the one that shrank.

**Rationale.** An exclusion list is robust to the templates this list omits (bare-reason and UI
callbacks). A new progress line in a future FieldWorks would be over-counted, which is safe and
visible, rather than a load error hidden.

## R-06 -- Running hc: streaming, timeout, cancellation, kill-survival (FR-016, FR-020)

**Decision.**
- The script starts `hc` with `System.Diagnostics.Process`:
  - `StandardOutputEncoding = [Text.Encoding]::Unicode` (F-1);
  - asynchronous `OutputDataReceived` writing each line to `hc-stdout.txt` through a UTF-8, no-BOM
    `StreamWriter` with `AutoFlush = $true`;
  - stderr the same way into `hc-stderr.txt`;
  - `WaitForExit(TimeoutSeconds * 1000)`.
- **On timeout** the script runs `taskkill /T /F /PID <hc>`, drains the reader, and writes
  `run.json` with `timed_out: true` and the in-flight index. The in-flight word is the last
  `Parsing "..."` or `Testing "..."` header without a terminating blank line.
- **Python** tails `hc-stdout.txt`, polling every 100 ms, and hands each complete block to the
  runner as that word's result. So `words_completed` advances live, and results survive any kill:
  they are already in `results.jsonl`.
- **Cancellation** is the existing cooperative path. `SandboxClient.cancel_run` kills the
  PowerShell process tree through `subprocess_helpers._kill_process_tree`, which takes `hc` with
  it. The partial results are already recorded.
- A Python-side watchdog, `TimeoutSeconds + 30`, backstops a script that fails to enforce its own
  timeout.

**Outcome mapping (FR-016, FR-018)**:
- exit code -1 with a `Load Error:` or `IO Error:` line is a start failure. It is reported with
  hc's message: the run is `failed`, and no word gets a parse result (US3 scenario 5);
- a block ending in `No valid parses.` is `not_parsed`;
- a block with `Parse <n>` sections is `parsed`;
- `The word contains an invalid segment at position <n>.` is `invalid_segment` with that position;
- a header followed by no terminator before the stream ends is `error_no_output` for the in-flight
  word and `not_reached` for every word after it;
- `not_expressible` comes from `dispatch.json`, and the word is never sent.

**Counters (FR-017).** The script appends `stats -p` for a parse and `stats -t` for a test.
Python parses `# of parses: N, successful: S, failed: F, error: E` or the test form, and compares
it with the per-word tally:

| Counter | Per-word tally it must equal |
|---|---|
| successful | parsed |
| failed | not_parsed |
| error | invalid_segment |

A mismatch is appended to the existing `counter_divergences` (CP3 field), and neither side is
preferred. The comparison is skipped on a timeout, where no counters print, and that is recorded as
`counters: "unavailable_timeout"`.

## R-07 -- Plugging into the job model without a second execution path (FR-035)

**Decision.** Add a new `SANDBOX_ROLE` and a `SandboxClient` that implements the worker-client
interface the runner already calls: `start`, `parse_word`, `cancel_run`, `is_running`,
`listen_to_run`, `stop_listening`, `terminate`, `aclose`.
- `start` does the engine check (when it applies), the free-space check, the cache lookup or
  generation, and launches `-Mode Parse` or `-Mode Test` for the **whole** list.
- `parse_word` awaits the next streamed block and returns it as that word's result. It returns
  immediately for a word `dispatch.json` marked not expressible.
- `ParseRunner.start_run` gains a branch: `worker_role == SANDBOX_ROLE` builds a fresh client per
  run instead of calling `WorkerPool.get` (F-13). `_execute_run` is otherwise unchanged.
- Stages reuse `starting -> loading_grammar -> parsing -> terminal`. `loading_grammar` covers both
  generation and hc's load banner.

**Rationale.**
- Status polling, the fast path, cancellation, retention and `results.jsonl` all come for free.
- The only new branch is how the client is obtained, which is smaller than CP4's four filing
  branches.

**Alternatives considered.**
- *A separate `SandboxRunner`.* Rejected: it is the "second execution path" FR-035 forbids.
- *One hc process per word.* Rejected: it reloads the grammar per word. That is minutes of overhead
  on a real grammar, and it breaks `stats`.

## R-08 -- Reading hc's parse columns (FR-019)

**Decision.**
1. Split the `Morphs: ` and `Gloss:  ` lines after their 8-character prefixes.
2. Tokenise each on runs of spaces.
3. Accept the reading only if the token counts are equal **and** re-rendering them with F-6's rule
   reproduces both lines exactly. The rule is: pad each column to `max(u16len(form), u16len(gloss))`
   and join with one space, with trailing padding allowed.

Otherwise the parse is `unreadable`. The raw two lines are kept, and there is no guess. That covers
an empty form, a form or gloss containing a space, and any misalignment. `u16len(s) =
len(s.encode("utf-16-le")) // 2`.

**Rationale.** The round-trip check makes "readable" a proof, not a heuristic. An unreadable parse
still counts toward `parsed` and toward the analysis count. It is just not diffable morph by morph.

## R-09 -- Word lists and the hc script (FR-013..FR-015, FR-027)

**Decision.**
- **Python (FR-015):** NFC-normalise, count occurrences **within the supplied list**, which is the
  only count source CP5 has, de-duplicate, sort by `(-count, word)`, cut to `limit`, record
  `truncated_by_limit`, and write `words.txt` (UTF-8, no BOM, one per line).
- **The script (FR-013, FR-014):**
  - reads `-WordFile` with `Get-Content -Encoding UTF8`;
  - splits `-Words` on `[,\s]+`, verbatim, for stand-alone use;
  - quotes each word. A word without `"` gets `"<w>"`. A word with `"` and no `'` gets `'<w>'`. A
    word with both, an empty word, or a word with a tab, CR or LF is `not_expressible`;
  - writes the hc script with `[IO.File]::WriteAllLines(..., (New-Object Text.UTF8Encoding($false)))`,
    verbatim.
- **A leading `-`**: `parse` has no options, so Mono.Options should pass the word through
  **[LIVE L-2]**. Until L-2 confirms it, a leading-`-` word is sent **and** flagged
  `leading_dash_unverified` in its result. If L-2 fails, the rule becomes `not_expressible`.
- **Tests:** each assertion becomes `test -p <f:g|f:g> [-p ...] [--] "<word>"`. `--` is emitted
  only for a leading-`-` word **[LIVE L-2]**.
- **FR-027**: an assertion is `not_expressible` if any form or gloss contains `|`, `:`, `\`, `'`,
  `"` or whitespace, or if an expected parse has zero morphs (F-5). An empty form is allowed; an
  empty gloss is written as `?` (F-7).

## R-10 -- Corpus files and seeding (FR-030..FR-033)

**Decision.** A corpus is a user-owned JSON file at
`~/.flextoolsmcp/parse/corpora/<project>/<name>.json`. JSON rather than a line format because it is
unambiguous for forms containing any character, and it is editable with ordinary tools. Its
schema is in data-model section 5.

Seeding (`action="seed_corpus"`) reads a **completed** sandbox parse run:
- `parsed` becomes its readable analyses, in the order hc printed them;
- `not_parsed` becomes `expected: []`, "no parse";
- every other outcome (`unreadable`, `invalid_segment`, `error_no_output`, `not_reached`,
  `not_expressible`) is **left out**, listed in the seed response with its reason, never silently
  dropped.

Classification comes from F-8's sections:

| Expected section | Actual section | Classification |
|---|---|---|
| `None` | `None` | `pass` |
| missing | `None` | `regression` |
| `None` | extras | `new_ambiguity` |
| missing | extras | `changed` |

An assertion with `expected: []` that now parses is `new_ambiguity` with `label: "now_parses"`
(FR-033). `error` covers invalid segment, not expressible, `error_no_output`, `not_reached` and a
timeout.

**Diff buckets (FR-032):** `regression` goes to `broken`, `new_ambiguity` and `changed` go to
`changed`, `pass` goes to `unchanged`, and `error` goes to `not_compared`.

## R-11 -- Paths, the copy, and the sweep (FR-008, FR-011, FR-012, FR-042)

**Decision.** There is a new root `~/.flextoolsmcp/parse/`, with an env override
`FLEXTOOLSMCP_PARSE_SANDBOX_DIR`, copying `record.get_record_dir()`'s pattern. It holds:
- `config-cache/<project>/<cache_key>/` (parent 5.5);
- `sandboxes/<project>/<name>/`;
- `corpora/<project>/`;
- `work/<run_id>/`, for the project copies.

Every root is passed through `filing/paths.py:assert_outside_project` at use, including overrides.

- **The copy (FR-008)** is an **allowlist**, not an exclusion list: `<name>.fwdata` plus
  `WritingSystemStore\**`. **[LIVE L-1]** settles whether `GenerateHCConfig` needs anything else.
  Candidates are `ConfigurationSettings\` and `SharedSettings\`, and any additions are made to the
  allowlist. The lock marker, `.hg`, `LinkedFiles`, `Backups` and everything else are therefore
  excluded by construction.
- **Free space (FR-012)**: at least `2 x sum(allowlisted sizes)` on the `work/` volume, checked
  before the directory is created. This reuses the rule of `backup._space_skip_reason`, with a
  different measure.
- **Always deleted (FR-011)**, three ways:
  1. the script's `finally`;
  2. `SandboxClient`'s own `finally`, after the script exits **or is killed**, because a tree-kill
     skips the script's `finally`;
  3. a sweep before a server's first sandbox job, which removes every `work/<id>/` containing the
     marker `.flextoolsmcp-sandbox-work` whose run is not live in this server.
- **Deletion** retries a Windows sharing violation 3 times, 200 ms apart. A copy still undeletable
  after that is recorded in the run (`copy_cleanup: "failed"` plus the path) and swept next time,
  never hidden.

## R-12 -- Cache key, lock, prune, invalidation (FR-024..FR-026)

**Decision.** `cache_key = sha256(canonical JSON of {fwdata_abspath, fwdata_size, fwdata_mtime_ns,
gen_path, gen_size, gen_mtime_ns, hcparse_version})[:16]`. The recipe is `fingerprint_key`'s.
`$script:HCPARSE_VERSION` is read from the packaged script's text at import, with the regex
`^\$script:HCPARSE_VERSION\s*=\s*'([^']+)'`. There is one source of truth, and a test pins that
the constant exists.

Each entry has `hc-config.xml`, `generate-config.log` and `key.json`. `key.json` holds:
- the key inputs;
- `created_at` and `last_used_at`;
- `load_errors`;
- `active_parser`;
- `invalidated_at`;
- versions.

- **Build once**: an in-process `asyncio.Lock` per `(project, cache_key)`. Generation writes into
  `<key>.partial/` and is atomically renamed into place. A second job waits on the lock and then
  finds the entry.
- **Prune**: keep 3 per project, ordered by `last_used_at`, oldest first. An entry referenced by a
  live run (an in-process refcount) is never deleted. Prune runs at each job start.
- **Invalidate (FR-026)**: set `invalidated_at` on every entry for the project. Lookups skip
  invalidated entries and prune deletes them. A job already running keeps its loaded config, which
  hc read at start. There are two call sites:
  1. the CP4 filing observer's `after_terminal` (`filing/observer.py:151`), beside
     `mark_read_worker_stale`;
  2. `run_module`, after a write-enabled run completes without error (`handlers/execution.py`,
     after the `run_script_async` block at ~4595). That module currently has no parse import. The
     import is lazy and guarded, so a sandbox import failure can never break `run_module`.
- **`-ConfigOut` confinement**: the only caller that passes `-ConfigOut` is
  `sandbox/cache.py:build_entry`, and it passes a `.partial` path under `config-cache/`. An AST test
  pins this. The script itself **refuses** a `-ConfigOut` that resolves under the `sandboxes/`
  root, as a second, independent gate.

**Rationale.** The mtime in the key already catches non-shared writes. Explicit invalidation
covers a write that lands inside the mtime resolution, and the shared case, where the in-memory
commit log is ahead of `.fwdata` (parent 7.3).

## R-13 -- Staleness and "held by another program" (FR-040)

**Decision.** Sandbox runs use `SANDBOX_STALENESS_VERDICTS = {open_shared, open_exclusive,
held_by_other}`. The in-process spines' `shared_mode_active` is **left unchanged**. The diff
downgrades `no_change` when **either** run's recorded `project_state.staleness` is
`shared_mode_unverifiable`. That is an additive rule; the existing rule is kept.

**Rationale.** Widening the in-process rule would change CP3's shipped verdicts for a case CP3's
spec did not ask about. Whether `held_by_other` should also downgrade in-process diffs goes into
the pattern audit (plan, sweep 3), not into this change.

## R-14 -- Cross-spine diffs (FR-039)

**Decision.**
- A sandbox run records a `scope_fingerprint` with `scope_kind="words"` and `engine="HC"`,
  so it passes `check_comparable` against an in-process `scope_kind="words"` run.
- The spine, config source and engine versions live in the new `spine` and `sandbox` meta fields,
  not in the fingerprint, so the fingerprint's meaning is unchanged.
- `diff.py` adds a `comparison` block: `{same_spine, same_config_source, same_engine_version,
  note}`, with a fixed sentence whenever any of them is false.
- Signatures for sandbox analyses use the existing `RENDERED_FALLBACK` mode. A sandbox analysis
  sets `signature: null` and `rendered_morphs` to its **forms**. The CP3 line shape
  (`artifact.md` section 4) holds forms only in `rendered_morphs`, with no glosses.
  - A **cross-spine** diff therefore compares form sequences. It says so in `comparison.note`:
    "compared by morph forms only; glosses and HVO-level identity are not compared across spines".
  - A **sandbox-to-sandbox** diff compares `(form, gloss)` sequences through the additive `morphs`
    key, the finer comparison.

**[CHECK in Phase 5]**: how `signature.py:129-173` picks its mode when one side has a signature
and the other does not. The adapter forces `RENDERED_FALLBACK` for any cross-spine pair rather
than trusting the auto-selection.

## R-15 -- Live verification needs a working hc, and this machine has none (FR-045)

**Fact.** This machine has the .NET 8.0.23 runtime only: no SDK, no .NET 10, no `hc`. FR-045
cannot run here as it stands.

**Decision.** This is a maintainer decision, **M-1** in the plan. There are two ways to get a
working `hc`:
1. Install a .NET SDK and the .NET 10 runtime, then run the install hint. That gives the current
   `hc`, 3.9.x, which is skewed against FieldWorks' 3.8.2.
2. **Without an SDK**: download the `SIL.Machine.Morphology.HermitCrab.Tool` **3.7.x** `.nupkg`
   from nuget.org (it is a zip), extract `tools/net8.0/any/`, and set `HC_TOOL_PATH` to its
   `hc.dll`. That runs on the installed .NET 8 runtime through `dotnet hc.dll`. It exercises the
   `.dll` form of R-03 and the version-skew warning. It does **not** give SC-003's
   matching-version parity.

The plan schedules live verification as `needs_human` until one of them is done. Downloading and
installing are outward-facing actions, so the MCP never performs them (Out of Scope), and this
session does not either without authorisation.

## R-16 -- The error surface (FR-007, FR-009, and what the spec did not name)

**Decision.**
- `parser_tool_missing` is emitted for both components. For `hc`, the hint is the verbatim command
  followed by: " Installing it needs a .NET SDK, and hc 3.8 and later need the .NET 10 runtime to
  run."
- `parser_config_failed` is new, with fields in the spec's order.
- `parser_timeout` gets its first emitter, through `RunFailure.detail`.

**A gap the spec leaves.** Six refusals need a code, and none exists in the 34:
1. an invalid sandbox or corpus name;
2. creating over an existing name;
3. an unknown sandbox or corpus;
4. seeding from a run that is not a completed sandbox parse;
5. insufficient disk space;
6. a malformed corpus file.

The spec names only one new code. The default taken is **one** additive code,
`parse_sandbox_refused`, with a closed `reason` enum and fields in this order:

`reason`, `name`, `path`, `hint`, then `needed_bytes`, `free_bytes`, which are null unless the
reason is disk space.

That brings the count from 34 to 36. It is additive and stays within `tool-responses/1.0`, but the
spec did not list it, so it is **maintainer decision M-2**.

**Alternative.** *Six codes.* Rejected: it multiplies the surface for one tool, and CP6 owns the
catalogue prose. *No new code, returning `runtime_error`.* Rejected by Principle V: a stable,
teachable code is required.
