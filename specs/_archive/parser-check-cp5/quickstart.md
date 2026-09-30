# Quickstart: parser-check CP5 live questions and verification scenarios

**Status.** This is the plan for live work. None of it has been run.

**M-1 is resolved (2026-09-24), not the way this file originally assumed.** The prerequisite is no
longer "a working `hc`" (research R-15's two routes to one). The maintainer's direction: call the
FieldWorks engine directly, in-process, from a `--sandbox` mode of the parse worker
(`HANDOFF.md`, `contracts/sandbox-worker.md`). The live prerequisite is now:

- FieldWorks 9 installed, with `SIL.Machine.Morphology.HermitCrab.dll` (FileVersion 3.8.2.0 on the
  reference machine -- the same engine Try A Word uses) and `GenerateHCConfig.exe` present under
  the FieldWorks install directory;
- no `hc` console tool, no `.NET SDK`, and no `.NET 10` runtime are required at all -- those were
  the retired spine's prerequisites (`contracts/hcparse.md`).

This machine already satisfies the revised prerequisite (`HANDOFF.md` "proven facts"): the engine
loads in a pythonnet `netfx` process with an `AppDomain.AssemblyResolve` handler pointed at the
FieldWorks folder, `XmlLanguageLoader.Load` + `Morpher` + `ParseWord` succeed, and a 62 KB config
loads and compiles in about 0.25s.

**Harness.** `tests/test_parse_live_cp5.py`, marked `requires_flex`. With `FLEXLIBS_REQUIRE_LIVE=1`
a missing prerequisite fails; without it, the test skips.

**Evidence.** It goes under `specs/parser-check-cp5/evidence/`. Each file records the versions of
FR-005: FieldWorks' HermitCrab (`fieldworks_hermitcrab_version`), GenerateHCConfig, and hcparse.
~~The hc tool~~ is retired from this list along with the retired spine (`contracts/hcparse.md`).

**Projects.**

| Project | Used for |
|---|---|
| `IndonesianHC-Complete` | correctness |
| `Malay Parsing-20230810withHC` | timeout and scale |
| `Sena 3` | the XAmple refusal only. The tool must refuse before any copy, so the project is never opened |
| `Circumsanity` | **New (D4 reversed, FR-050)**: the id-map/shaping live check (L-6, S14), a circumfix project. Used only via a scratch copy (`tests/live_support/make_disposable.py`), never the project itself |

**Safety.** The sandbox spine never writes the project. Every scenario still records a
**byte-identity hash** of the whole project folder before and after (FR-043, SC-001). The one
scenario that needs a project *write* (S9, cache invalidation) runs on a disposable copy made with
`tests/live_support/make_disposable.py`. That helper's prefix is generalised from `CP4-Scratch-`
to a parameter, and CP5 uses `CP5-Scratch-`.

---

## Live questions (run first; each can change code)

**Dropped (CP5 re-plan 2026-09-24): L-2, L-3, L-5.** These existed only for the retired `hc`
console-tool spine -- word-quoting and the leading-dash rule (L-2), the `hc` stdout UTF-16 BOM
(L-3), and the .NET-host-missing-runtime error text (L-5), all `contracts/hcparse.md` concerns
with no equivalent in the sandbox worker's JSON-over-stdio channel (`contracts/sandbox-worker.md`).
A wordform is a plain JSON string field now, with no quoting to verify; the worker's own channel
encoding is fixed and owned by this codebase (`_force_utf8_stdio`), not hc's piped console; and
there is no separate .NET runtime for the engine to be missing (D7, `data-model.md` section 7).

| # | Question | How | Changes if the answer is no |
|---|---|---|---|
| L-1 | Which project files does `GenerateHCConfig` need? | Generate from an allowlist copy (`.fwdata` + `WritingSystemStore`). If it fails, add `ConfigurationSettings`, then `SharedSettings`, one at a time. Diff the result against a config generated from a **full** copy (identical bytes expected) | The allowlist in `sandbox/workdir.py` and the free-space measure |
| L-4 | Does `GenerateHCConfig` hang offline (SLDR)? | Disable the network and generate | The default of `-GenerateTimeoutSeconds` and its hint text |
| L-6 | At matching HermitCrab versions, do sandbox results equal Try A Word's (SC-003)? | Compare the same 20 words through `flextools_try_word` and the sandbox, including at least one word needing a guessed root (SC-003(b)), one whose `ParserParameters` are non-default (SC-003(c)), and one whose analysis involves a circumfix or a `FormID==0`/unresolvable id, run against `Circumsanity` (under `C:\ProgramData\SIL\FieldWorks\Projects`) via a **scratch copy only** (`tests/live_support/make_disposable.py`) to validate the `lcm-ids.json` HVO-order assumption (research.md D4) | **Reworded (D4 reversed, maintainer correction 2026-09-24)**: circumfix doubling, `FormID==0` skipping, and unresolvable-id dropping are now expected to **match** Try A Word exactly (FR-050), not to differ. If they do not match, that is a bug in the shaping rules or the id map, not an expected difference; only SC-003(d)'s two remaining named differences (glosses from `Morpheme.Gloss`, and user-added morphs in a named sandbox) stay expected |
| L-7 | Can the live `.fwdata` be stream-read and copied while FLEx holds the project open, exclusively and shared? | Open it in FLEx, then run S7 | If not, the engine check and the copy report `project_locked`, and FR-036's hint changes |

---

## Scenarios

**Revised (CP5 re-plan 2026-09-24).** S2 is **dropped**: it existed only to observe `hc`'s
`runtime_missing` signal (an installed `hc` with no matching .NET runtime), and D7 has no such
state to observe -- the engine either loads from a FieldWorks install already present on the
machine, or it does not, with no separate runtime dependency in between (`data-model.md`
section 7). S1, S3, S4, S8 and S11 are revised in place, below, to the engine vocabulary; S5
through S7, S9, S10, S12 and S13 are unaffected (they exercise Generate mode, the run-record
machinery, and the health/refusal ordering, none of which depended on `hc` specifically).

| # | Story | Setup | Expect | Evidence file |
|---|---|---|---|---|
| S1 | US1 | FieldWorks not installed, or `SIL.Machine.Morphology.HermitCrab.dll` missing from it | `sandbox.status: unavailable`; the `fieldworks_hermitcrab` component has `found: false`; the guidance names the repair-FieldWorks hint and **never** `flextools_parse_sandbox`; the tool refuses with `parser_tool_missing`, and `install_hint` matches `contracts/tools.md` section 4's `fieldworks_hermitcrab` text | `s1-health-no-engine.json` |
| ~~S2~~ | ~~US1~~ | ~~`hc` 3.8+ present, no .NET 10~~ | **Dropped (CP5 re-plan 2026-09-24).** No equivalent state exists for an in-process engine (above) | -- |
| S3 | US1 | FieldWorks installed with the HermitCrab engine present | `ready`; `fieldworks_hermitcrab_version` and `generate_hc_config_version` reported; no skew advisory (there is only one engine version to report, `contracts/tools.md` section 6) | `s3-health-ready.json` |
| S4 | US2 | Parse a non-Latin list including an apostrophe word and a known failure | One result per word; the apostrophe word is parsed as one word (there is no quoting layer left to trip on it, `contracts/sandbox-worker.md` section 3); no "invalid segment at position 1"; the counters agree; project hash identical; `work/` empty | `s4-parse-words.json` |
| S5 | US2 | Repeat S4 | `generation.reused_cache: true`; wall time at most half of S4's (SC-006) | `s5-warm-cache.json` |
| S6 | US3 | Create sandbox `tighten-env`, edit one `LeftEnvironment`, run S4's words, diff against S4 | The sandbox path is outside the project; the diff runs and shows the change; creating the same name again is refused | `s6-sandbox-rehearse.json` |
| S7 | US2, US3 | FLEx holds the project with sharing on, then with sharing off | The run proceeds from a copy; sharing on gives `staleness: shared_mode_unverifiable` | `s7-held-by-flex.json` |
| S8 | US4 | Seed a corpus from S4's run. Break one rule in a sandbox so word A loses its only parse; loosen another so word B gains a parse. Run the corpus | Exactly one `regression` (A, listing the missing parse) and one `new_ambiguity` (B, listing the extra parse); totals equal the worker's own `engine_counters` (`data-model.md` section 6.6, replacing hc's `stats -t`) | `s8-corpus-regression-ambiguity.json` |
| S9 | US6, FR-026 | Disposable copy: create sandbox X; run once to warm the cache; perform a `run_module` write; run again | The cache entry is invalidated and regenerated; sandbox X is byte-identical before and after (SC-007) | `s9-invalidation-sandbox-untouched.json` |
| S10 | US5, FR-020 | Malay project, 100 words, `timeout_seconds` low enough to cut the run at about 40 | `parser_timeout`; `words_completed` about 40; the in-flight word named; those results readable through `parse_log`; `work/` empty | `s10-timeout-partial.json` |
| S11 | US5 | Hand-break the sandbox XML and run | The **first** `parse` of the run fails with `parser_job_failed`, `failure: "engine_unavailable"` (`contracts/sandbox-worker.md` section 5, replacing hc's `Load Error:` in `hc_stdout`); zero parse results | `s11-broken-sandbox.json` |
| S12 | US2 | `Sena 3` (XAmple) | `parser_engine_mismatch` before any copy; the project folder is not opened (the hash is identical, and no lock file appears during the call) | `s12-xample-refused.json` |
| S13 | US6 | Kill the server process mid-run, restart it, run one sandbox job | The orphaned `work/<id>` is removed by the sweep | `s13-orphan-sweep.json` |
| S14 | US2, US3 | **New (D4 reversed, FR-050)**: parse `Circumsanity` (scratch copy) so a circumfix word and a word whose analysis needs an id absent from the live project are both included; separately, hand-add a morph with no `ID` to a named sandbox and parse it | The circumfix pair is emitted once, flagged `is_circumfix: true`; the unresolvable-id analysis is dropped entirely (never partially shaped); the hand-added morph is emitted flagged `user_added: true` and does not cause its analysis to be dropped | `s14-shaping-circumfix.json` |
| S15 | US1, US2 | **New (D4 reversed, FR-050)**: hand-corrupt a cache entry's `lcm-ids.json` (an id pointed at the wrong class) and parse | The run fails as `parser_job_failed`, `failure: "id_map_invalid"`, before any word is parsed; a run against a cache entry with no `lcm-ids.json` at all (a pre-FR-050 fixture) instead parses normally with `meta.sandbox.shaping.id_map: "absent"` | `s15-id-map-invalid.json` |

**Exit.**
- L-1, L-4, L-6, L-7 are answered and folded into code (L-2, L-3, L-5 dropped above);
- S1, S3 through S15 have evidence files (S2 dropped above; S14/S15 new, D4 reversed/FR-050);
- the full suite is green (SC-010).

If the FieldWorks HermitCrab engine is not available on the machine running the live phase, it
stops as `needs_human` and does not downgrade to mocks (constitution, quality gates).
