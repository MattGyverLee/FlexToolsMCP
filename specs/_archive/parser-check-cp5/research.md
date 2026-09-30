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

**Re-plan note (2026-09-24, see `HANDOFF.md`).** M-1 ("how do we get a working `hc`") is resolved by
dropping the `hc` CLI: Parse and Test now run in-process, in a `--sandbox` mode of the parse worker,
against FieldWorks' own bundled `SIL.Machine.Morphology.HermitCrab.dll`. R-03, R-06, R-08, R-09 and
R-15 are marked superseded below, in place, rather than deleted -- each records what it superseded and
why. **R-17**, at the end of this file, is the re-plan's own research entry: the options compared for
where Parse/Test should run, and decisions D1-D8.

---

## Source facts the design rests on

These come on top of the six facts in the spec's Summary. Each one changes code.

| # | Fact | Evidence | Consequence |
|---|---|---|---|
| F-1 | `hc` sets `Console.OutputEncoding = Encoding.Unicode`, so its piped stdout is **UTF-16LE**, not UTF-8 | `Program.cs:14-15` (checked by hand) | **Superseded (CP5 re-plan 2026-09-24).** Moot for Parse/Test: there is no `hc` stdout to decode, since the sandbox worker returns .NET objects directly. Kept as a fact about the `hc` tool itself, for historical accuracy |
| F-2 | Without `-s`, `hc -i x` goes interactive and blocks on `Console.ReadLine()`. With no `-i`, `-h` or no args, it prints usage and exits -1 without reading stdin | `Program.cs:98-113, 37-51` | **Superseded (D2).** The identity probe this justified (`hc -h`) is retired along with `hc` discovery; see R-17/D2 |
| F-3 | The usage text starts `Usage: hc [OPTIONS]` / `HermitCrab.NET is a phonological and morphological parser.` `hc` has no version option | `Program.cs:164-167` | **Superseded (R-03 below, D7).** There is no `hc` identity to recognise from usage text any more |
| F-4 | The `-o` writer is `new StreamWriter(file)`: UTF-8, AutoFlush off, flushed only on `Close()`. The console writer flushes on every write | `Program.cs:58` | **Superseded (R-06 below).** Moot: the sandbox worker never invokes `hc -o`; there is no `-o` writer in this design at all |
| F-5 | `test` parses `-p` values outside its `try`. A morph without `:` throws, the `finally` never runs, and `_expectedParses` **leaks into the next `test`** | `TestCommand.cs:31, 107` | **Superseded.** Moot: there is no `hc test` command and no shared mutable `_expectedParses` state between assertions; corpus comparison is a Python-side structural comparison per assertion (FR-027, reworded) |
| F-6 | `WriteParse` pads each column to `max(len(form), len(gloss))`, as .NET `string.Length`, i.e. **UTF-16 code units**, and joins columns with a single space. An empty gloss prints as `?` (`MorphInfo.cs:25-26`) | `Extensions.cs:274-304` | **Superseded (R-08 below).** Moot for reading: the sandbox worker reads each morph's form and gloss directly from the .NET `Word`/`Morpheme` objects (domain review, `morph_infos`), never from printed, padded columns. The `?`-for-empty-gloss convention (`MorphInfo.cs`, `Morpheme.Gloss`) is kept as the semantic rule (D4), just read from the object instead of parsed from text |
| F-7 | `MorphInfo.Equals` compares form and gloss, where the gloss is already `?`-substituted | `MorphInfo.cs:39-41` | **Unaffected in substance.** A seeded expectation `form:?` still round-trips exactly (R-10), because the `?`-for-empty convention is preserved (D4), only the read mechanism changed |
| F-8 | On failure `test` prints only the **unmatched** expected parses and the **unmatched** actual parses, or `None` | `TestCommand.cs` | **Superseded as a mechanism, kept as a shape.** There is no `hc test` failure output to read; FR-031's classification now compares the recorded expected analyses against the worker's returned analyses directly as sets, which reproduces the same missing/unexpected shape without the CLI's report format |
| F-9 | `GenerateHCConfig`'s `ConsoleLogger` writes **one line per grammar error**, in seven fixed templates plus bare-reason and UI-callback lines, interleaved with four fixed progress lines | `ConsoleLogger.cs` | **Unaffected.** Generate mode is unchanged; a load error is still any line that is not one of the known progress lines (R-05) |
| F-10 | `ConsoleLogger.UnmatchedReduplicationIndexedClass` throws `NotImplementedException`, so one ill-formed reduplication index crashes the generator | `ConsoleLogger.cs:204-207` | **Unaffected.** A crash still has no `Writing completed.` line, so it becomes `parser_config_failed`. The hint names the static grammar scan |
| F-11 | `check_active_parser` reads `ActiveParser` through LCM, and its only caller is the worker, which **opens the project** | `parser_probe.py:788`, `worker_main.py:911-938` | **Unaffected, strengthened by D6.** FR-036 still needs a path that does not open LCM (R-02), and the re-plan adds: it must also run **before the sandbox worker process is spawned**, not just before any copy |
| F-12 | `RunRecord.read_meta` **silently drops** any key that is not a `RunMeta` field, and every stage change rewrites the meta | `record.py:513-514` | **Unaffected, and now covers more fields.** `spine` and `sandbox` must be declared `RunMeta` fields, the way CP4 declared `filing`; the re-plan adds `parser_parameters`, `parameters_applied`, `parameters_source` (D3/FR-047) to that same list of fields that would silently vanish if left undeclared |
| F-13 | `WorkerPool` keys workers by `(project, role)` | `worker_client.py:827-870` | **Unaffected.** Two concurrent sandbox jobs on one project would share a pooled client if pooled. The sandbox client (and its sandbox worker process) is built **per run**, outside the pool (R-07) |
| F-14 | `parser_timeout` and `parser_tool_missing` have detail models but **no emitter anywhere** | `response_models.py:439, 626`; grep | **Unaffected, with an addition.** CP5 is still their first emitter; the re-plan adds a third first-emitted detail model, `ParserJobFailedDetail` (`failure: engine_unavailable`, D7), for the "DLL present but fails to load" case |
| F-15 | CP1's boundary tests forbid any argv containing `hc`, and the dynamic test fakes `subprocess.run` with empty stdout | `tests/test_cp1_boundary.py:234, 814, 826, 1403` | **Superseded (R-04 retired; see D2 below).** FR-003 (which would have run `hc`) is retired outright, since there is no `hc`. The CP1 boundary instead gains a differently-shaped, narrower exception: `Morpher` / `XmlLanguageLoader.Load` permitted only inside `worker_main.py`'s `--sandbox` mode, via a pinned `CP5_SANDBOX_ENGINE_ALLOWLIST` (D2). The QC review (cycle 1, P0) flags that without this pin, `test_the_worker_still_constructs_no_parser_itself` would be vacuously green rather than actually enforcing the boundary |
| F-16 | `diff.shared_mode_active` covers `open_shared` and `open_exclusive`, **not `held_by_other`** | `diff.py:74, 130` | **Unaffected.** FR-040 names "held by another program". R-13 decides how that is handled |
| F-17 | USAGE.md has no row for `flextools_parse_cancel` (drift from CP4) | grep | **Unaffected.** Fixed in the same change as the sandbox row |

---

## R-01 -- What the script owns and what Python owns

**Reworded (CP5 re-plan 2026-09-24).** This section described the original mechanism/policy split
for a design where `hcparse.ps1` ran Parse and Test as well as Generate. It is kept for the parts
that still hold (Generate mode; Principle VI's "one owner" reasoning) and superseded for the parts
that described `hc`. The re-plan's own version of this split is R-17.

**Decision (Generate mode only; Parse/Test superseded).** The script, `hcparse.ps1`, is the
**mechanism** for Generate mode. It does these things and nothing else:
- makes the minimal copy into a work directory the MCP names;
- runs `GenerateHCConfig` with its output captured;
- deletes the copy in `finally`.

~~turns a word list or assertion file into an `hc` script (quoting, and the not-expressible
check); runs `hc` under a timeout, streaming its decoded console output to a flushed UTF-8 file;
kills the process tree on timeout; writes `dispatch.json` before `hc` starts and `run.json` at the
end~~: **superseded (CP5 re-plan 2026-09-24)**. That is now the sandbox worker's job (R-17), not the
script's.

Python is the **policy**. It owns:
- discovery (now: locating the bundled DLL, not `hc`);
- the engine check (D6: now also gates spawning the sandbox worker, not just the copy);
- the free-space check;
- the cache (key, lock, prune, invalidation; now also carries `hc_parameters`, D3);
- sandbox and corpus files;
- word-list ordering (dedup, NFC, limit);
- ~~the single parser of hc's output~~ **superseded**: there is no `hc` output text to parse; the
  worker returns structured data directly;
- classification (now: direct structural comparison, not `hc`'s test-command sections);
- the run record.

~~The script is invoked twice per cold job, in two modes... A warm job invokes it once.~~
**Superseded (CP5 re-plan 2026-09-24).** The script now has one mode, Generate, invoked at most once
per cold job (skipped entirely on a warm job). Parse/Test are a separate sandbox worker process,
launched by `SandboxClient` once per run regardless of cache warmth.

**Rationale (kept where it still applies).**
- Principle VI: each rule has exactly one owner. ~~Quoting lives only in the script, next to the H11
  encoding lessons~~: superseded, there is no quoting left to own (FR-013 retired). H11's word-list
  splitting still lives in the script for the string-list-to-JSON-list step (FR-014). Output
  reading/interpretation lives only in the sandbox worker and Python, where it is unit-testable and
  where the job runner needs it per word as results arrive.
- The cache lock still covers generation only (unaffected): a single invocation holding the lock for
  the whole parse would make a second job on the same grammar wait hours for a config that was ready
  in seconds. This reasoning now applies to "the script's Generate invocation" vs. "the sandbox
  worker's run", not to two modes of one script.

**~~Reading FR-023 ("per-word results")~~. Superseded (CP5 re-plan 2026-09-24).** FR-023 no longer
describes Parse/Test at all (it is narrowed to Generate mode's `run.json`). The per-word
interpretation question this section flagged for the maintainer -- "does the script classify, or does
Python?" -- is answered definitively by the re-plan: the sandbox worker (Python-side, inside the
existing worker process) produces the structured analyses directly from the .NET objects. There is no
second format to parse, so the divergence risk this section warned about cannot arise for Parse/Test.

**Alternatives considered (historical, for the original script-driven Parse/Test).**
- *Python does everything and the script is dropped.* This is close to what happened, except "Python"
  turned out to mean "the existing parse worker process, in `--sandbox` mode" rather than new
  free-standing Python calling a still-external `hc`. The script survives for Generate mode alone,
  where the "maintainer runs it by hand" argument still holds.
- *The script parses and classifies.* Superseded along with `hc` itself: there is no `hc` output for
  the script to parse any more.

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

**Updated (CP5 re-plan 2026-09-24, D6).** The check's ordering guarantee is now stated more strongly:
it MUST run before any copy **and before any sandbox worker process is spawned**. This matters
because, unlike the original design, spawning a sandbox worker is itself now a meaningful cost and a
process-isolation boundary (FR-046) -- a mismatched-engine project should never even get a worker
process started on its behalf. The check stays server-side, in `server/sandbox/engine.py`; it never
moves into the sandbox worker itself (which would reintroduce exactly the "does the worker assume a
project" problem D1 exists to prevent).

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

**Superseded (CP5 re-plan 2026-09-24, D7).** This entire section described discovering, identifying
and probing a stand-alone `hc` tool. There is no such tool any more: the sandbox worker loads the
FieldWorks-bundled `SIL.Machine.Morphology.HermitCrab.dll` directly, at a path the MCP's existing
`versioning.get_resolved_fieldworks_dir()` resolution already knows. Kept below, struck through in
substance rather than deleted, for the record of what CP5 originally designed here. The re-plan's
replacement is D7 (see R-17): health checks only DLL presence and `FileVersion`, spawning nothing.

**~~Decision.~~** ~~`discover_hc_tool` gains a recorded `source` and the four-step order of FR-001:~~
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

**Superseded (CP5 re-plan 2026-09-24, D2).** FR-003 (the `hc -h` identity probe this section
narrowed the boundary for) is retired outright -- there is no `hc` to probe. The CP1 boundary still
needs an exception, but a differently-shaped one: `Morpher` and `XmlLanguageLoader.Load`, permitted
only inside `worker_main.py`'s `--sandbox` mode, via `CP5_SANDBOX_ENGINE_ALLOWLIST` (D2, R-17). The
QC review (cycle 1, finding P0) is why this is a *pinned* allowlist rather than a silent gap: without
it, `test_the_worker_still_constructs_no_parser_itself` would pass only because `Morpher` /
`XmlLanguageLoader` were never in the forbidden-names list to begin with, not because the worker
actually avoided constructing them. Kept below for the record of the originally-designed exception.

**~~Decision.~~** ~~CP1's "never shells out to the parser" invariant is **narrowed**, not dropped:~~
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

**Superseded (CP5 re-plan 2026-09-24).** This section designed a script-driven `hc` subprocess with
UTF-16 stdout streaming, `taskkill`, and a counter-reconciliation step. None of that exists in the
re-plan: the sandbox worker calls `ParseWord` in-process and returns structured results directly over
the worker's existing JSON-lines protocol; timeout/cancellation kill the worker process itself, not a
`hc` process beneath a script (FR-020, reworded); and there are no separate `hc` counters to
reconcile against (FR-017, reworded -- see R-17). Kept below for the record.

**~~Decision.~~**
- ~~The script starts `hc` with `System.Diagnostics.Process`:~~
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
- `start` does the engine check (when it applies, D6), the free-space check, the cache lookup or
  generation, and **spawns a sandbox worker process (`--sandbox` mode)** for the run
  (**reworded, CP5 re-plan 2026-09-24**: ~~launches `-Mode Parse` or `-Mode Test` for the **whole**
  list~~).
- `parse_word` awaits the next message from the sandbox worker's JSON-lines protocol and returns it
  as that word's result. ~~It returns immediately for a word `dispatch.json` marked not
  expressible~~: superseded, every word is sent (FR-013 retired).
- `ParseRunner.start_run` gains a branch: `worker_role == SANDBOX_ROLE` builds a fresh client per
  run instead of calling `WorkerPool.get` (F-13). `_execute_run` is otherwise unchanged.
- Stages reuse `starting -> loading_grammar -> parsing -> terminal`. `loading_grammar` covers both
  generation and the sandbox worker's engine load (~~hc's load banner~~).

**Rationale.**
- Status polling, the fast path, cancellation, retention and `results.jsonl` all come for free.
- The only new branch is how the client is obtained, which is smaller than CP4's four filing
  branches.

**Alternatives considered.**
- *A separate `SandboxRunner`.* Rejected: it is the "second execution path" FR-035 forbids.
- ~~One hc process per word.~~ **Superseded (CP5 re-plan 2026-09-24), rationale reused for the new
  design**: reloading the engine per word would still cost minutes of overhead on a real grammar
  (the domain review measured ~190ms for a first parse of a 62KB config, dominated by load), which
  is exactly why the sandbox worker's `Morpher` is loaded once per run and kept for the run's
  duration (D1: `release()` keeps it), not reloaded per word.

## R-08 -- Reading hc's parse columns (FR-019)

**Superseded (CP5 re-plan 2026-09-24).** This entire section designed a round-trip column-decoder
for `hc`'s printed, space-padded text output. It is moot: the sandbox worker reads each morph's form
and gloss directly from the .NET `Word`/`Morpheme` objects (the domain review's `morph_infos`
walk), so there are no printed columns to misread and no "unreadable" classification to compute.
Kept below for the record; the `u16len` insight is not wasted -- it is exactly the reason .NET
`string.Length` (UTF-16 code units) matters when comparing forms/glosses that may contain
astral-plane characters, which the direct-object read sidesteps rather than needing to guard against.

**~~Decision.~~**
1. ~~Split the `Morphs: ` and `Gloss:  ` lines after their 8-character prefixes.~~
2. ~~Tokenise each on runs of spaces.~~
3. ~~Accept the reading only if the token counts are equal **and** re-rendering them with F-6's rule
   reproduces both lines exactly.~~

## R-09 -- Word lists and the hc script (FR-013..FR-015, FR-027)

**Partially superseded (CP5 re-plan 2026-09-24).** The word-**ordering** decision (Python, FR-015)
is unaffected and still holds exactly as written. Everything about quoting the words *for `hc`*
(the script's job below) is superseded: words now travel as JSON string values over the worker
protocol, so there is no quoting, no `not_expressible`, no leading-dash question, and no `test -p`
command line to build. FR-027's escaping rule is replaced by a schema-validity check (spec.md,
reworded). Kept below for the record.

**Decision.**
- **Python (FR-015, unaffected):** NFC-normalise, count occurrences **within the supplied list**,
  which is the only count source CP5 has, de-duplicate, sort by `(-count, word)`, cut to `limit`,
  record `truncated_by_limit`, and hand the ordered list to the sandbox worker as a JSON list
  (**reworded**: ~~write `words.txt` (UTF-8, no BOM, one per line)~~ -- that was for the script's
  `-WordFile`, which no longer applies to Parse/Test).
- ~~**The script (FR-013, FR-014):**~~ **Superseded.**
  - ~~reads `-WordFile` with `Get-Content -Encoding UTF8`~~;
  - splits `-Words` on `[,\s]+`, verbatim, for stand-alone use (**kept**: FR-014 preserves this for
    the string-list-to-JSON-list step, now done in Python before the worker call, not the script);
  - ~~quotes each word...~~ **retired**;
- ~~A leading `-`: `parse` has no options, so Mono.Options should pass the word through **[LIVE
  L-2]**...~~ **Moot.** There is no CLI option parser in the path any more; a leading-`-` word is
  just a JSON string like any other.
- ~~Tests: each assertion becomes `test -p <f:g|f:g> [-p ...] [--] "<word>"`...~~ **Moot.** Corpus
  assertions are sent as structured data and compared as structured data (R-10).
- ~~FR-027: an assertion is `not_expressible` if any form or gloss contains `|`, `:`, `\`, `'`, `"`
  or whitespace...~~ **Superseded.** No delimiter is unexpressible any more (FR-027, reworded); the
  `?`-for-empty-gloss convention (F-7) is unaffected in substance.

## R-10 -- Corpus files and seeding (FR-030..FR-033)

**Decision.** A corpus is a user-owned JSON file at
`~/.flextoolsmcp/parse/corpora/<project>/<name>.json`. JSON rather than a line format because it is
unambiguous for forms containing any character, and it is editable with ordinary tools. Its
schema is in data-model section 5. Unaffected by the re-plan.

Seeding (`action="seed_corpus"`) reads a **completed** sandbox parse run:
- `parsed` becomes its readable analyses, in the order the sandbox worker returned them
  (**reworded**: ~~the order hc printed them~~ -- there is no print order, but the worker's own
  return order is preserved the same way);
- `not_parsed` becomes `expected: []`, "no parse";
- every other outcome (~~`unreadable`~~ retired with R-08, `invalid_segment`, `error_no_output`,
  `not_reached`; ~~`not_expressible`~~ retired with FR-013) is **left out**, listed in the seed
  response with its reason, never silently dropped. **New (D5)**: a `guessed` morph is seeded like
  any other -- it is not excluded or specially marked at seed time, only at classification time is it
  compared as its own category (SC-003(b)).

Classification comes from **direct structural comparison** (**reworded**: ~~F-8's sections~~ -- the
same missing/unexpected shape F-8 described for `hc test`'s report, now computed directly in Python
by comparing the recorded expected analyses against the worker's returned analyses as sets, since
there is no `hc test` report to read the shape from):

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
- versions;
- **New (CP5 re-plan 2026-09-24, D3)**: `hc_parameters` -- the project's `ParserParameters/HC`
  settings, read at generation time by the same stream-read `engine.py` does for the `active_parser`
  check. **Not** part of the cache key (FR-025, reworded): the exported grammar and the Morpher
  parameters that get applied to it at parse time are independent axes, so a parameters-only change
  does not need regeneration.

- **Build once**: an in-process `asyncio.Lock` per `(project, cache_key)`. Generation writes into
  `<key>.partial/` and is atomically renamed into place. A second job waits on the lock and then
  finds the entry.
- **Prune**: keep 3 per project, ordered by `last_used_at`, oldest first. An entry referenced by a
  live run (an in-process refcount) is never deleted. Prune runs at each job start.
- **Invalidate (FR-026)**: set `invalidated_at` on every entry for the project. Lookups skip
  invalidated entries and prune deletes them. A job already running keeps its loaded config, which
  the sandbox worker read at start (**reworded**: ~~which hc read at start~~). There are two call
  sites:
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

**Resolved (CP5 re-plan 2026-09-24). M-1 is closed, not by either option this section originally
proposed.** See `HANDOFF.md` and R-17 below for the maintainer's actual decision. Kept here, struck
through, for the record of what was tried and rejected before the re-plan.

**~~Fact.~~** ~~This machine has the .NET 8.0.23 runtime only: no SDK, no .NET 10, no `hc`. FR-045
cannot run here as it stands.~~ Still a true fact about this machine's runtime, but no longer a
blocker: the sandbox worker needs no SDK, no .NET 10, and no separately-installed `hc` at all. It
loads FieldWorks' own bundled `SIL.Machine.Morphology.HermitCrab.dll` (3.8.2 in FW 9.3.11) through
pythonnet, running under whatever .NET the MCP server process itself already uses.

**~~Decision.~~** ~~This is a maintainer decision, **M-1** in the plan. There are two ways to get a
working `hc`:~~
1. ~~Install a .NET SDK and the .NET 10 runtime, then run the install hint. That gives the current
   `hc`, 3.9.x, which is skewed against FieldWorks' 3.8.2.~~ **Rejected** (option 3 of `HANDOFF.md`'s
   three, in the sense that it was never pursued): this session did not have authorisation to
   perform an outward-facing install, and it would still have left a skewed engine.
2. ~~**Without an SDK**: download the `SIL.Machine.Morphology.HermitCrab.Tool` **3.7.x** `.nupkg`
   from nuget.org...~~ **This was tried and worked** (`HANDOFF.md`'s "option 1 of 3", packaged as
   `reference/hc_fw_prototype.py` / `hc_fw.py`), but the maintainer **rejected it** once it worked,
   because it duplicates `hc`'s own program and `hc_output.py` would have to track `hc`'s exact text
   format across every SIL.Machine or FieldWorks update -- the same "two parsers of one format"
   divergence risk R-01 originally flagged, now realised as the reason to not ship it.

~~The plan schedules live verification as `needs_human` until one of them is done.~~ **Superseded.**
The maintainer's own framing, recorded verbatim in `HANDOFF.md`: "we've been calling the parser, why
do we need all this new architecture?" -- i.e., stop trying to get a **separate** `hc` running at
all, and call the engine FieldWorks already has, from the process that already knows how to talk to
a parser (the worker). See R-17.

## R-16 -- The error surface (FR-007, FR-009, and what the spec did not name)

**Decision.**
- `parser_tool_missing` is emitted for both components. ~~For `hc`, the hint is the verbatim command
  followed by: " Installing it needs a .NET SDK, and hc 3.8 and later need the .NET 10 runtime to
  run."~~ **Superseded (CP5 re-plan 2026-09-24, D7).** There is no `hc` component any more. For the
  bundled HermitCrab DLL, the hint instead points at repairing or reinstalling FieldWorks.
- `parser_config_failed` is new, with fields in the spec's order. Unaffected (Generate mode).
- `parser_timeout` gets its first emitter, through `RunFailure.detail`. Unaffected in shape; now
  fires for the sandbox worker's own timeout rather than `hc`'s.
- **New (CP5 re-plan 2026-09-24, D7)**: `parser_job_failed` (`failure: engine_unavailable`) is a
  distinct code from `parser_tool_missing`, for the case health could not have caught: the DLL is
  present, but the sandbox worker's `XmlLanguageLoader.Load` (or the `AssemblyResolve` handler)
  fails at run time. Conflating this with `parser_tool_missing` would say "not found" about a file
  that health had just reported present, which is actively misleading (Principle V). This is a
  **second** additive code beyond the spec's original list, alongside `parse_sandbox_refused` (M-2
  below) -- bringing the count to 37, not 36.

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

That brings the count from 34 to 36 (37 with `parser_job_failed` above). Both are additive and stay
within `tool-responses/1.0`, but the spec did not list either, so `parse_sandbox_refused` is
**maintainer decision M-2**; `parser_job_failed` is part of the D7 design-of-record decision, not a
separately-numbered open question, since it follows directly from the maintainer's own re-plan.

**Alternative.** *Six codes.* Rejected: it multiplies the surface for one tool, and CP6 owns the
catalogue prose. *No new code, returning `runtime_error`.* Rejected by Principle V: a stable,
teachable code is required.

---

## R-17 -- Sandbox parsing in the parse worker (CP5 re-plan, 2026-09-24)

**Context.** T095 (the live checks) was `needs_human`, blocked on M-1: "how do we get a working
`hc`". Live investigation this session (`HANDOFF.md`) established that FieldWorks 9 ships the
**engine** (`SIL.Machine.Morphology.HermitCrab.dll`, 3.8.2 in FW 9.3.11 -- the same DLL Try A Word
uses) and `GenerateHCConfig.exe`, but **not** the `hc` console tool, and that this machine has no
.NET SDK and only the .NET 8 runtime (`hc` 3.8+ needs .NET 10). "Found on disk" and "able to run"
were never actually going to describe the typical FLEx machine's *normal* state, as R-15 assumed;
they describe its **permanently absent** state, because `hc` was never meant to be end-user
software.

**Options compared.**

1. **A packaged `hc` stand-in (`hc_fw.py`), run by `hcparse.ps1`.** Built and proven live this
   session (`reference/hc_fw_prototype.py`, `reference/hc-host-attempt.diff`): it loads the engine
   via pythonnet `netfx` plus an `AssemblyResolve` handler, and emulates `hc`'s `parse`/`test`
   commands and text output closely enough that the original script-driven design (R-01, R-06, R-09)
   could have run against it unchanged. **Rejected** by the maintainer once it worked: it duplicates
   `hc`'s own program, and `hc_output.py` (R-08) would have to track `hc`'s exact text format across
   every SIL.Machine or FieldWorks update -- the "two parsers of one format" divergence risk R-01
   flagged, realised in the worst way (a home-grown *third* format pretending to be a *first*, to be
   read by a *second*).
2. **A `--sandbox` mode of the existing parse worker (`worker_main.py`), calling the engine
   in-process.** **Chosen.** One parse path (the worker already has a `ParseWorker` loop and a
   JSON-lines protocol; sandbox parsing reuses both, rather than adding a second text protocol to
   parse). No copy of `hc`'s program to maintain. No parsing of `hc`'s text output, ever -- the
   worker reads .NET objects directly. No command-language escaping (FR-013, FR-027 retired). This
   is the maintainer's own framing, verbatim: "we've been calling the parser, why do we need all this
   new architecture?"
3. **Drop sandbox parsing altogether**, keeping only Generate mode (export without a parse rehearsal
   loop). **Rejected**: it deletes the spine's actual value (User Story 3, "rehearse" rung of the
   confidence gradient), which #166 exists to deliver.

**Alternatives within option 2, also considered and rejected:**
- *A pool-worker message on the existing project-bound worker*, rather than a new `--sandbox` mode.
  Rejected: every existing message handler on that worker assumes a live project (`preflight()`,
  `resolve`, `engine_check`, etc. -- QC review section 2), and retrofitting "sometimes there's no
  project" through all of them is a larger, riskier change than a distinct mode with its own,
  smaller message surface (D1).
- *Opening the copy via `project.Parser`/flexicon*, so the existing in-process spine's own code path
  parses the sandbox copy. Rejected: it opens an LCM project (even if only the sandboxed copy), which
  reintroduces exactly the write-adjacent risk profile (Principle I) the sandbox spine exists to
  avoid, and it cannot honestly claim FR-046's process isolation.
- *The rejected `hc` stand-in itself* (option 1 above), kept as `reference/` material for its
  proven engine-loading code (`Engine.__init__`'s `AssemblyResolve` handler), its `morph_infos`
  per-morph extraction logic, and its test-command matching semantics -- all reused inside the new
  `_SandboxBackend`, just not wrapped in an `hc`-emulating shell.

**Decisions.**

- **D1 (message scope).** In `--sandbox` mode, the worker refuses project-bound messages: `resolve`,
  `engine_check`, `resolve_scope`, `parser_parameters` (as a client-supplied override), `agent_probe`,
  `filing_*`, and `restricted_to` (spec.md FR-049). Internal hooks other code unconditionally calls
  stay neutral rather than raising: `preflight()` is a no-op, `active_engine()` returns `None`,
  `eligible_entries()` reports `known=False`. `release()` keeps the loaded `Morpher` rather than
  reloading it between words (QC review section 3 confirmed `_release_if_idle` fires after every
  word in the real backend; the sandbox backend deliberately does not inherit that per-word churn,
  since reloading costs the ~190ms first-parse load every time).
- **D2 (CP1 boundary).** Add `Morpher` and `XmlLanguageLoader.Load` to the guarded vocabulary via a
  pinned `CP5_SANDBOX_ENGINE_ALLOWLIST`, scoped to `worker_main.py` only. Remove the `hc -h`
  identity-probe machinery (R-03, R-04's originally-planned narrowing) entirely, since there is no
  `hc` left to probe.
- **D3 (engine parameters).** Apply `ParserParameters/HC` to the Morpher: `DelReapps` ->
  `DeletionReapplications`, `MaxRoots` -> `MaxStemCount`, `MergeAnalyses` ->
  `MergeEquivalentAnalyses`, `GuessRoots` -> `ParseWord`'s `guessRoot` argument, `MaxAlternatives`
  only if the loaded `Morpher` has it (**[verified v3.8.2 by the domain review]**: absent in 3.8.2,
  present from 3.9.1). FLEx defaults when absent: `0`/`2`/`true`/`true`/`0`. Source priority: `key.json`
  `hc_parameters` (cache run) > a live `.fwdata` stream read (named sandbox run against its
  originating project) > FLEx defaults. Record `parser_parameters`, `parameters_applied`,
  `parameters_source` (spec.md FR-047).
- **D4 (Try A Word shaping, domain review section 2). Reversed (maintainer correction, 2026-09-24):
  D4 originally named these as permanent gaps; they are FLEx's own display rules
  (`HCParser.GetMorphs`, `C:\Github\fieldworks\Src\LexText\ParserCore\HCParser.cs:332-440`), not
  bugs, and CP5 replicates them.** Per morph of each analysis, in order:
  a. skip a morph whose allomorph `Property` `ID` (FormID) is absent or `0`;
  b. an `AffixProcessAllomorph` with no `ID2` whose form's morph type is circumfix
     (`kguidMorphCircumfix`): the first occurrence is recorded and emitted; the second
     occurrence is emitted too, as the suffix portion (LT-21447, the two-sided "Leipzig" circumfix
     case) (corrected 2026-09-24 against `HCParser.cs:347-374`: FLEx emits **both** occurrences -- the first is recorded *and* emitted, so the circumfix shows before and after what it attaches to);
  c. a morpheme already seen is emitted again only if it is the APR-circumfix suffix portion
     (keyed on `ID`) or has `ID2 > 0` (a two-part circumfix, keyed on `ID2`); otherwise it is
     skipped;
  d. the whole analysis is dropped if a form ID, the morpheme's MSA `ID`, or a positive
     `InflTypeID` does not resolve.

  **How.** The exported config XML carries only the `Property` `ID` (and `ID2`/`InflTypeID` when
  present) and **no morph type** -- verified this session against `IndonesianHC-Complete`: every
  one of its 82 exported ids is an LCM HVO from `GenerateHCConfig`'s own session, and equals the
  1-based document order of the corresponding `<rt>` element in the `.fwdata` `GenerateHCConfig`
  loaded (e.g. ID 4918 = `rt` #4918, the `MoStemAllomorph` "ŋeoŋ"; the 82 ids resolve to 40
  `MoStemAllomorph`, 40 `MoStemMsa`, 1 `MoAffixAllomorph`, 1 `MoDerivAffMsa`). This is an LCM
  XML-backend load-order behaviour, **not** a documented contract, so it is fragile by
  construction -- see the new "HVO order assumption" risk in `plan.md`.

  **Design.** During Generate mode, the MCP (server-side, a plain stream read of the byte-identical
  `work/<run_id>/` copy, never through LCM) writes a sidecar `lcm-ids.json` into the cache entry
  beside `hc-config.xml`: for every id referenced by the config, `{guid, class, morph_type_guid}`
  (`morph_type_guid` only for `MoForm` subclasses, read from the object's `MorphType` `objsur`). It
  **validates**: every `FormID`/`ID2` must resolve to a `MoForm` subclass, every MSA `ID` to a
  `MoMorphSynAnalysis` subclass, and every `InflTypeID` to a `LexEntryInflType`. Any miss marks the
  whole mapping **invalid**, and the run then fails as `parser_job_failed` (`failure:
  "id_map_invalid"`) -- never a silent skip of shaping. The worker receives the sidecar's path
  (`--id-map <json>`) and applies rules a-d against it; "resolves" in rule (d) means "present in
  this validated map". `key.json` records the sidecar's path; it is part of the cache entry, and a
  named sandbox copies it at creation the same way it copies the rest of the cache entry's inputs
  (FR-028, spec.md FR-050).

  **User-edited sandbox exception.** A morpheme or allomorph a user hand-adds to a named sandbox's
  `hc-config.xml` has no `ID` at all. Rule (a) does not apply to it: it is emitted, flagged
  `user_added: true`, and rule (d) does not drop an analysis on its account. A morph whose `ID` is
  present but absent from the validated map still follows rule (d) (dropped, with its analysis).

  Gloss is `Morpheme.Gloss`, `?` if empty -- the `hc`/`MorphInfo` convention (F-6, F-7), read
  directly from the .NET object rather than parsed from printed text. This remains a named
  difference from Try A Word (spec.md SC-003(d)), since Try A Word shows live LCM senses instead.
- **D5 (guessed roots, domain review section 3).** Per-morph `guessed` comes from
  `word.GetAllomorph(morph).Guessed` **[verified v3.8.2: `Morpher.cs:400`;
  `RootAllomorph.cs:46 IsPattern`]** -- the reliable signal, not the fragile "gloss equals form"
  heuristic. Corpus classification does not special-case guessed morphs (spec.md FR-048).
- **D6 (engine-check ordering).** FR-036's engine check stays server-side, in
  `server/sandbox/engine.py` (R-02's stream read, never through LCM), and now runs before any copy
  **and** before the sandbox worker process is spawned -- not just before the copy, as originally
  scoped. A mismatched-engine project should never get a worker process started on its behalf at
  all.
- **D7 (health and run-time failure, domain review section 4 + QC review considerations).** Health
  checks only DLL presence and a readable `FileVersion` -- no process spawn, no load attempt. This is
  deliberately weaker than R-03's original "cannot start" probe, and that is the point: there is
  nothing to spawn or probe safely and cheaply for an in-process engine the way `hc -h` could be run
  and killed. A DLL that is present but fails to load (a corrupt install, a missing
  `SIL.Core`-version dependency the `AssemblyResolve` handler cannot find, etc.) surfaces on the
  **first sandbox run**, as `parser_job_failed` (`failure: engine_unavailable`) -- not as a health
  finding. The version-skew advisory (R-03, Q3) is removed outright, not merely never triggered:
  there is no independently-installed engine version to be skewed against, since the sandbox worker
  loads FieldWorks' own DLL.
- **D8 (scope).** #223's per-word reopen/reload question is about `_RealBackend` and is out of scope
  for CP5; the sandbox backend's own per-run (not per-word) load discipline is D1's `release()`
  behaviour, not a fix for #223.

**Evidence this session already produced**, referenced by the decisions above (`HANDOFF.md`):
- The engine loads in a pythonnet `netfx` process (targets netstandard2.0; references `SIL.Core` 17
  against FieldWorks' shipped 18, resolved by the `AssemblyResolve` handler).
- Load plus compile of a 62KB config: ~0.25s; first parse: ~190ms; later parses: ~50ms. This is the
  quantitative case for D1's "keep the Morpher loaded per run" choice.
- `GenerateHCConfig.exe` on a scratch copy of `IndonesianHC-Complete`: 2.7s. `pukul` -> `pukul/hit`;
  `memukul` -> `mem-ukul VBL-hit`. The orthography is IPA, so Latin test words hit invalid-segment
  errors -- a live fixture consideration for quickstart's word-list choices, not a design constraint.
