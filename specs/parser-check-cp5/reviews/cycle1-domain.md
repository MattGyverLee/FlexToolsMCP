# Domain Expert Review -- parser-check CP5, cycle 1

**Date:** 2026-09-24
**Spec reviewed:** `specs/parser-check-cp5/spec.md`
**Reviewer:** `lex-domain` (read-only; this file was saved by the dispatching session)
**Score:** 91/100
**Status:** APPROVED. There are no BLOCKING findings; the non-blocking notes are below.

## Sources read

- `C:\Github\machine\src\SIL.Machine.Morphology.HermitCrab.Tool\`: `Program.cs`, `TestCommand.cs`,
  `ParseCommand.cs`, and the `.csproj`
- `C:\Github\fieldworks\Src\GenerateHCConfig\`: `Program.cs`, `ConsoleLogger.cs`,
  `ProjectIdentifier.cs`, `NullFdoDirectories.cs`, and `GenerateHCConfig.csproj`
- `src/flextoolsmcp/server/response_models.py`
- parent `specs/parser-check/SPEC.md` section 14
- earlier CP2 and CP4 evidence

liblcm is not cloned in this workspace.

## The six source-derived claims

1. **The SDK and .NET 10 prerequisites: CONFIRMED.** The current checkout's
   `SIL.Machine.Morphology.HermitCrab.Tool.csproj:5` says `net10.0`. The reviewer could not read
   git tags and so could not re-derive the tag boundary. The dispatching session had already checked
   it with `git show <tag>:...csproj`: `v3.7.0` targets `net8.0`, and `v3.8.0` and `v3.9.4` target
   `net10.0`.
2. **Quote-toggle splitting: CONFIRMED** (`Program.cs:139-160`).
   - An unquoted `don't` splits into `don` and `t`.
   - A double-quoted `"don't"` survives, because the `'` branch is guarded by `!inDoubleQuote`.
   - A word containing both quote characters cannot be expressed.
3. **The broken backslash escape: CONFIRMED** (`TestCommand.cs:111-127`). `continue` in the
   `do...while` skips `start = end + 1`, so `start` never advances.
   - *Reviewer:* this is an infinite loop.
   - *Session note:* when the escaped delimiter is found while `start == 0`, the loop condition
     `start > 0` is false, so the loop exits instead, and the expectation is silently truncated. The
     spec's wording, "loop forever or silently truncate", covers both cases.
4. **GenerateHCConfig exit codes, and the config still being written after load errors:
   CONFIRMED.**
   - Help exits 0 (`Program.cs:24`), and so does success (`:54`).
   - Its three anticipated failures exit 1: file not found (`:27-31`), locked (`:56-62`), and
     migration forbidden (`:63-69`).
   - Anything else is an unhandled crash.
   - `ConsoleLogger`'s `IHCLoadErrorLogger` methods only call `Console.WriteLine`, so the load
     continues and `XmlLanguageWriter.Save` still runs.
   - `"Writing completed."` (`:52`) is a real line to match on.
5. **HermitCrab 3.8.2 bundled in FW 9.3.11: CONFIRMED.** The reviewer confirmed that the DLL is
   present, and confirmed the version by citing earlier evidence
   (`specs/parser-check-cp4/evidence/q4-checker-reprobe.json:64,85`). The dispatching session read
   `FileVersionInfo` directly: 3.8.2.0.
6. **Buffered `-o` output lost on a kill: CONFIRMED.** `new StreamWriter(outputFile)`
   (`Program.cs:58`) does not flush automatically. The console writer, by contrast, flushes on every
   write. Output that goes to the console (no `-o`) therefore survives a kill far better.

## Other findings

- **FR-016, non-blocking.** `hc` also returns -1 for command-line errors (`Program.cs:37-51`), not
  only when a configuration fails to load. **Applied:** FR-016 now says -1 means a failure to start,
  usually a load failure.
- **Output buffering, non-blocking.** The kill-survival difference between console output and
  `-o` output should be explained. **Applied:** a new Assumptions bullet covers it.
- **FR-008, informational.** Which files the generator needs cannot be settled from source.
  `ProjectIdentifier.ProjectFolder` is the `.fwdata`'s directory, and
  `CreateCacheFromExistingData` lives in liblcm, which is not cloned here. The live verification
  in FR-045 must settle it by experiment. The spec's existing hedge is correct.
- **Copied `.fwdata.lock`, informational.** FR-008 already leaves the lock marker out of the copy,
  so the question does not need answering.
- **ActiveParser from a copy, informational.** `ActiveParser` sits inside the XML text of the
  `MoMorphData.ParserParameters` string property. It is not an element of its own in the `.fwdata`
  file (`parse/measure.py:177-210`, `worker_main.py:669`). An absent or unreadable value falls back
  to XAmple (CP2 `reviews/cycle1-domain.md:118-122`). **Applied:** the Assumptions bullet now says
  it is read in two steps or through LCM, and fails safe.
- **Words beginning with `-`, informational.** Whether ManyConsole or Mono.Options passes such a word
  through intact cannot be settled from source, because the package is not vendored. The spec's
  "(unverified; verify live)" is correct.

## Error contract: names and field order

| Code | Parent SPEC 14 | CP5 spec | response_models.py |
|---|---|---|---|
| `parser_engine_mismatch` | `configured_engine, supported_engines, hint` | same | `:399-402` same |
| `parser_tool_missing` | `component, expected_path, install_hint` | same | `:447-450` same |
| `parser_config_failed` | `exit_code, stderr_tail, log_path, run_id` | same, marked new | absent (new) |
| `parser_timeout` | `timeout_seconds, words_completed, run_id, hint` | same | `:640-644` same |

The contract stays at `tool-responses/1.0` (`docs/TOOL-CONTRACT.md:3`). The `HC_TOOL_PATH`
override already exists in `parser_probe.py`.
