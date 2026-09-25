# Quickstart: parser-check CP5 live questions and verification scenarios

**Status.** This is the plan for live work. None of it has been run.

**It is blocked on M-1**: this machine has the .NET 8 runtime only, with no SDK, no .NET 10 and no
`hc`. See research R-15 for the two routes to a working `hc`.

**Harness.** `tests/test_parse_live_cp5.py`, marked `requires_flex`. With `FLEXLIBS_REQUIRE_LIVE=1`
a missing prerequisite fails; without it, the test skips.

**Evidence.** It goes under `specs/parser-check-cp5/evidence/`. Each file records the three
versions of FR-005: the hc tool, FieldWorks' HermitCrab, and GenerateHCConfig.

**Projects.**

| Project | Used for |
|---|---|
| `IndonesianHC-Complete` | correctness |
| `Malay Parsing-20230810withHC` | timeout and scale |
| `Sena 3` | the XAmple refusal only. The tool must refuse before any copy, so the project is never opened |

**Safety.** The sandbox spine never writes the project. Every scenario still records a
**byte-identity hash** of the whole project folder before and after (FR-043, SC-001). The one
scenario that needs a project *write* (S9, cache invalidation) runs on a disposable copy made with
`tests/live_support/make_disposable.py`. That helper's prefix is generalised from `CP4-Scratch-`
to a parameter, and CP5 uses `CP5-Scratch-`.

---

## Live questions (run first; each can change code)

| # | Question | How | Changes if the answer is no |
|---|---|---|---|
| L-1 | Which project files does `GenerateHCConfig` need? | Generate from an allowlist copy (`.fwdata` + `WritingSystemStore`). If it fails, add `ConfigurationSettings`, then `SharedSettings`, one at a time. Diff the result against a config generated from a **full** copy (identical bytes expected) | The allowlist in `sandbox/workdir.py` and the free-space measure |
| L-2 | Does a word beginning with `-` reach `parse` intact? Does `test ... -- -word` work? | Parse `-an` against a grammar that parses it, then run the equivalent `test` | Leading `-` becomes `not_expressible`, and the `leading_dash_unverified` flag is removed either way |
| L-3 | Does piped hc stdout carry a UTF-16 BOM? Does PowerShell 5.1's `StandardOutputEncoding = Unicode` decode it cleanly? | Parse a non-Latin word, then inspect the raw bytes and `hc-stdout.txt` | The BOM handling in the script, and `run.json.hc.stdout_bom` |
| L-4 | Does `GenerateHCConfig` hang offline (SLDR)? | Disable the network and generate | The default of `-GenerateTimeoutSeconds` and its hint text |
| L-5 | What does the .NET host print when the runtime `hc` needs is missing (exit code, stderr text)? | Run `hc -h` for 3.8 on this machine before installing .NET 10 | The `runtime_missing` matcher in `parser_probe.py` |
| L-6 | At matching HermitCrab versions, do sandbox results equal Try A Word's (SC-003)? | Compare the same 20 words through `flextools_try_word` and the sandbox | If there is a difference, record it, and add the difference to `results_label`'s note |
| L-7 | Can the live `.fwdata` be stream-read and copied while FLEx holds the project open, exclusively and shared? | Open it in FLEx, then run S7 | If not, the engine check and the copy report `project_locked`, and FR-036's hint changes |

---

## Scenarios

| # | Story | Setup | Expect | Evidence file |
|---|---|---|---|---|
| S1 | US1 | No `hc` (the state now) | `sandbox.status: unavailable`; the hc component has `found: false`; the guidance names the install command and **never** `flextools_parse_sandbox`; the tool refuses with `parser_tool_missing`, and `install_hint` starts with the command | `s1-health-no-hc.json` |
| S2 | US1 | `hc` 3.8+ present, no .NET 10 | `found: true, starts: false, signal: runtime_missing`; the reason names the runtime; the tool refuses before any copy (the `work/` directory is unchanged) | `s2-health-cannot-start.json` |
| S3 | US1 | Working `hc` | `ready`; three versions reported; skew advisory present if they differ | `s3-health-ready.json` |
| S4 | US2 | Parse a non-Latin list including an apostrophe word, a both-quotes word and a known failure | One result per word; the apostrophe word is parsed as one word; the both-quotes word is `not_expressible`; no "invalid segment at position 1"; the counters agree; project hash identical; `work/` empty | `s4-parse-words.json` |
| S5 | US2 | Repeat S4 | `generation.reused_cache: true`; wall time at most half of S4's (SC-006) | `s5-warm-cache.json` |
| S6 | US3 | Create sandbox `tighten-env`, edit one `LeftEnvironment`, run S4's words, diff against S4 | The sandbox path is outside the project; the diff runs and shows the change; creating the same name again is refused | `s6-sandbox-rehearse.json` |
| S7 | US2, US3 | FLEx holds the project with sharing on, then with sharing off | The run proceeds from a copy; sharing on gives `staleness: shared_mode_unverifiable` | `s7-held-by-flex.json` |
| S8 | US4 | Seed a corpus from S4's run. Break one rule in a sandbox so word A loses its only parse; loosen another so word B gains a parse. Run the corpus | Exactly one `regression` (A, listing the missing parse) and one `new_ambiguity` (B, listing the extra parse); totals equal `stats -t` | `s8-corpus-regression-ambiguity.json` |
| S9 | US6, FR-026 | Disposable copy: create sandbox X; run once to warm the cache; perform a `run_module` write; run again | The cache entry is invalidated and regenerated; sandbox X is byte-identical before and after (SC-007) | `s9-invalidation-sandbox-untouched.json` |
| S10 | US5, FR-020 | Malay project, 100 words, `timeout_seconds` low enough to cut the run at about 40 | `parser_timeout`; `words_completed` about 40; the in-flight word named; those results readable through `parse_log`; `work/` empty | `s10-timeout-partial.json` |
| S11 | US5 | Hand-break the sandbox XML and run | The run fails with hc's `Load Error:` in `hc_stdout`; zero parse results | `s11-broken-sandbox.json` |
| S12 | US2 | `Sena 3` (XAmple) | `parser_engine_mismatch` before any copy; the project folder is not opened (the hash is identical, and no lock file appears during the call) | `s12-xample-refused.json` |
| S13 | US6 | Kill the server process mid-run, restart it, run one sandbox job | The orphaned `work/<id>` is removed by the sweep | `s13-orphan-sweep.json` |

**Exit.**
- L-1 through L-7 are answered and folded into code;
- S1 through S13 have evidence files;
- the full suite is green (SC-010).

If no `hc` is available, the live phase stops as `needs_human` and does not downgrade to mocks
(constitution, quality gates).
