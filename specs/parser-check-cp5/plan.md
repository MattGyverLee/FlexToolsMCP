# Implementation Plan: parser-check CP5 -- the sandbox spine

**Branch**: `feat/parser-check-cp5`, from `main` at `2772b52`

**Date**: 2026-09-24

**Spec**: [`spec.md`](./spec.md), over [`../parser-check/SPEC.md`](../parser-check/SPEC.md) sections 5.3, 5.5, 6.2, 7, 10, 10.1, 10.2, 13 and 14

**Predecessors**: CP1-CP4 on `main`. Issue #165 is a sequencing dependency only.

**Size**: `oversized`, so this is a full-tier plan. It touches a published contract (one new tool, one or two new codes) across many modules.

**Write path?** **No.** The spine never opens the live project through LCM and never writes a file
in any project folder. The one new write-adjacent behaviour is **cache invalidation** triggered by
existing writes, which deletes only MCP-owned cache files. The constitution's live-LCM *write*
verification therefore does not apply. FR-045's live run is still mandatory, and it is blocked on
M-1.

---

## Summary

CP5 turns the maintainer's `hcparse.ps1` into a packaged, hardened script behind a new read-only
tool, `flextools_parse_sandbox`. The tool exports the project's grammar from a minimal copy,
caches the exported configuration, and runs words or a corpus of expected parses through the
stand-alone `hc` tool. Users may also copy the export into a named, user-owned sandbox and edit it
freely. The live project is never opened or written.

The technical approach splits mechanism from policy (research R-01):
- **The PowerShell script** copies, generates, quotes, runs `hc` under a timeout, streams its
  output to flushed files, and always deletes the copy.
- **Python** owns everything else: discovery, the engine check, the cache and its three
  lifecycles, parsing `hc`'s output, and classification.
- **The job model is reused.** A per-run `SandboxClient` implements the worker-client interface, so
  status, the fast path, cancellation, retention, logs and diff come without a second execution
  path (R-07).

Reading the `hc` and `GenerateHCConfig` sources turned up facts the spec does not state, and each
is designed for (research F-1..F-17). Four matter most:
- `hc`'s console output is **UTF-16LE** (F-1).
- A malformed `test` expectation **leaks into the next test** (F-5).
- The run record **silently drops** undeclared meta keys (F-12).
- FR-003's identity probe collides with a **standing CP1 invariant** (F-15), which is narrowed
  rather than dropped (R-04).

No new language or dependency is added. `FileVersion` is read with `ctypes` against the Win32
version API, which is Windows-only by design (Principle VII).

---

## Scope fence

| Not in this slice | Where | Why |
|---|---|---|
| Expectations from human-approved analyses | deferred (Q2 default) | Seeding from a baseline run only (FR-030) |
| Refusing a skewed `hc` version | never, unless Q3 is overturned | Warn and label (FR-005) |
| `hc` tracing (`tracing on`) | follow-up | Not in the spec. Trace output would need its own parser and size cap |
| Word lists from a CP3 text scope | follow-up | Resolving a scope opens the live project through the worker (the lock, per memory note `non-shared-projects-single-opener`). CP5 takes explicit words or a word file |
| Deleting sandboxes or corpora through the tool | out | They are user-owned. `list` gives paths and the user deletes with ordinary tools |
| Installing `hc`, an SDK or a runtime | out (spec) | Named in hints, never performed |
| Contract prose, telemetry, user docs | CP6 (#167) | Only contract rows and the CHANGELOG paragraph land here |
| Widening `held_by_other` staleness to in-process diffs | pattern audit, sweep 3 | R-13 keeps CP3's verdicts unchanged |

---

## Technical Context

| | |
|---|---|
| **Language/Version** | Python 3.11+. Windows PowerShell **5.1** for the script (no PowerShell 7 syntax) |
| **Primary Dependencies** | External and discovered, never bundled: `hc`, the `SIL.Machine.Morphology.HermitCrab.Tool` dotnet tool (net10.0 from 3.8, net8.0 at 3.7.x); `GenerateHCConfig.exe` from FieldWorks 9. Internal: `pydantic` v2 detail models, the CP2b-CP4 job runner and run record |
| **Storage** | `~/.flextoolsmcp/parse/{config-cache,sandboxes,corpora,work}/` (override `FLEXTOOLSMCP_PARSE_SANDBOX_DIR`). Sandbox files under each run's `sandbox/` directory. **Nothing in a project folder** (FR-042) |
| **Testing** | `pytest`, offline by default. Script tests run PowerShell with **fake `hc` and fake generator** (small Python programs behind `.cmd` shims, emitting UTF-16LE where the real `hc` does). They are marked Windows-only. `requires_flex` live tests are gated by `FLEXLIBS_REQUIRE_LIVE` |
| **Target Platform** | Windows with FieldWorks 9 |
| **Constraints** | Contract stays `tool-responses/1.0`. The live project is never opened through LCM by this spine. Console output is ASCII. The CP1-CP4 standing tests stay green, apart from R-04's documented narrowing |
| **Scale/Scope** | 1 new tool, 1 new code (2 with M-2), 1 new package of 9 modules, 1 packaged script, extensions to 10 existing modules, and about 16 new test files |

---

## Constitution Check

*GATE: must pass before Phase 0 research, and is re-checked after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Safety-First Write Path** (NON-NEGOTIABLE) | **PASS / mostly N/A.** No database write exists on this spine, and it opens no LCM project. Enforcement is structural: `sandbox/` is added to the no-writes scans (`test_parse_no_project_writes.py`, `test_parse_no_edit_blocking.py`), and the inverse confinement test (`test_filing_write_confinement.py`) already covers all of `src/`. The copy happens outside project folders (FR-042) and is always deleted (FR-011). Cache invalidation on write completion **follows** the existing ladder and never gates or alters it, so an import failure there cannot break `run_module` (R-12). Stated plainly: these are safety properties, not a security boundary. A user can point `HC_TOOL_PATH` anywhere |
| **II. Discovery Over Memory** | **PASS / N/A.** No generated-module surface changes. `hc` and generator behaviour are taken from source (research F-table), and unknowns are **[LIVE]**, not assumed |
| **III. Self-Contained, Regenerable Extraction** | **PASS / N/A.** No index or extractor change. pyflexicon is untouched, so memory note `release-order-flexicon-first` does not apply |
| **IV. Append-Only Versioned Contracts** | **PASS.** Additive throughout: one tool; `parser_config_failed` (plus `parse_sandbox_refused`, pending M-2); two optional `RunMeta` fields; additive health keys; additive `results.jsonl` keys. The existing `parser_tool_missing` and `parser_timeout` shapes are unchanged. **No version floor**: skew is a warning, and the existing no-floor regression tests are extended to the three new versions. One CHANGELOG "Tool contract" paragraph |
| **V. Errors That Teach** | **PASS.** Every refusal names its next step: the install command plus prerequisites; the runtime to install; "repair FieldWorks"; the static grammar scan after a generation failure, timeout or load errors (FR-041); the space needed against the space free. Health tells "absent" apart from "cannot start" (FR-004). One code path writes both the human log (`generate-config.log`, `hc-stdout.txt`) and the structured record (`run.json` folded into `meta.json`) |
| **VI. One Module, One Source of Truth** | **PASS, with one justified tension.** Each rule has exactly one owner: quoting lives in the script, output parsing in Python, `HCPARSE_VERSION` in the script text (Python reads it). The job runner is reused, not paralleled (FR-035). **Tension**: two copies of the 2x free-space rule (backup and sandbox) measure different things. Resolution: extract `backup._space_skip_reason`'s rule into a shared `disk_space_ok(path, needed_bytes)` and have both callers use it. That is a small refactor, pinned by the existing backup tests passing unmodified |
| **VII. Windows-First** | **PASS.** Windows PowerShell 5.1, Win32 `FileVersion`, `taskkill /T /F`. The script tests are marked Windows-only and skip on the Linux smoke job. Console output is ASCII (FR-021). **Subprocess boundaries are encoding-explicit**: UTF-16LE from `hc` (F-1), UTF-8 files everywhere else. This is exactly the principle's "non-Latin data can never corrupt a result marker" |

**Quality gates.**
- *Pattern audit*: five sweeps, listed below.
- *Live verification*: mandatory for FR-045. It is read-path only, and a reference project is
  allowed, but every scenario still takes a byte-identity hash. It is **blocked on M-1**.
- *Merge requirements*:
  - the CHANGELOG entry;
  - golden fixtures for the new code or codes;
  - `validate_integrity.py server` clean, which needs the USAGE.md rows for both
    `flextools_parse_sandbox` and the drifted `flextools_parse_cancel` (F-17);
  - lint and pre-commit.

**Post-design re-check (after Phase 1).**
- There is no change from the table above.
- The design adds **no** `OpenProject` call and no write to a project folder. `sandbox/` joins the
  standing no-write scans.
- The CP1 narrowing (R-04) is not a constitution matter, but it does change a standing test. It is
  pinned by a new test that fails if discovery ever passes `-i`, `-s` or `-o`.

---

## Project Structure

### Documentation (this feature)

```text
specs/parser-check-cp5/
├── plan.md              # this file
├── spec.md              # written; lex-domain cycle 1 APPROVED
├── research.md          # F-1..F-17, R-01..R-16
├── data-model.md        # lifecycles, cache/sandbox/corpus schemas, record additions, health keys
├── quickstart.md        # L-1..L-7, S1..S13
├── contracts/
│   ├── tools.md         # arguments, check order, codes (field order authoritative), responses
│   └── hcparse.md       # script parameters, exit codes, dispatch.json, run.json, invariants
├── checklists/requirements.md
├── reviews/             # cycle1-domain.md; plan-gate QC lands here
├── evidence/            # live artifacts (blocked on M-1)
└── tasks.md             # /speckit.tasks -- NOT created here
```

### Source Code

```text
src/flextoolsmcp/
├── scripts/
│   └── hcparse.ps1                 # NEW -- packaged, hardened (contracts/hcparse.md). Replaces the root copy
├── server/
│   ├── sandbox/                    # NEW package -- the sandbox spine's policy
│   │   ├── __init__.py
│   │   ├── paths.py                # root + env override, per-project dirs, name validation, assert_outside_project (R-11)
│   │   ├── engine.py               # stream-read ActiveParser from the live .fwdata, no LCM (R-02)
│   │   ├── workdir.py              # allowlist measure, free-space check, marker, retrying delete, startup sweep (R-11)
│   │   ├── cache.py                # key, per-key asyncio lock, build via -Mode Generate, LRU prune, invalidate (R-12)
│   │   ├── script.py               # HCPARSE_VERSION reader; argv builder (never a string); run.json/dispatch.json loaders
│   │   ├── hc_output.py            # the ONE parser: blocks, columns (UTF-16 widths), counters, test sections (R-06, R-08)
│   │   ├── classify.py             # parse outcomes; assertion classification; diff-bucket mapping (R-10)
│   │   ├── store.py                # sandbox create/list/origin; corpus seed/load/validate (data-model 4, 5)
│   │   └── client.py               # SANDBOX_ROLE + SandboxClient (worker-client interface, per run) (R-07)
│   ├── parser_probe.py             # discover_hc_tool: 4 sources + recorded source; `hc -h` identity/startability; versions (R-03)
│   ├── handlers/
│   │   ├── diagnostic_health.py    # sandbox component keys, advisories, next_step rows; FR-006 rule (contracts 6)
│   │   ├── parse.py                # + handle_flextools_parse_sandbox; parse_log spine-aware (FR-038); diff comparison
│   │   └── execution.py            # + guarded, lazy cache invalidation after a successful write-enabled run_module (R-12)
│   ├── parse/
│   │   ├── record.py               # RunMeta + spine, sandbox (F-12); _child writes for sandbox/ files
│   │   ├── runner.py               # start_run: SANDBOX_ROLE builds a per-run client, not a pooled one (F-13); parser_timeout failure
│   │   ├── diff.py                 # comparison block (R-14); either-run staleness downgrade (R-13); assertion buckets
│   │   └── signature.py            # force RENDERED_FALLBACK for cross-spine pairs (R-14)
│   ├── filing/observer.py          # after_terminal: + invalidate the sandbox cache for the project (FR-026)
│   ├── backup.py                   # _space_skip_reason's rule extracted to a shared disk_space_ok (Principle VI)
│   ├── models.py                   # + ParseSandboxInput
│   ├── response_models.py          # + ParserConfigFailedDetail (+ ParseSandboxRefusedDetail, M-2); AnyDetail; docstring tally
│   ├── tool_definitions.py         # + flextools_parse_sandbox ToolDef
│   └── dispatch.py                 # + route (the six touch points of CP4's parse_cancel)
pyproject.toml / MANIFEST.in        # + "scripts/*.ps1" package data
hcparse.ps1 (repo root)             # DELETED (history kept); scripts/ralph/campaign.json references updated
docs/TOOL-CONTRACT.md               # + rows; count 34 -> 35 (36 with M-2)
USAGE.md                            # + flextools_parse_sandbox and flextools_parse_cancel rows (F-17)
CHANGELOG.md                        # one "Tool contract" paragraph + the new tool
specs/parser-check/SPEC.md          # 10.2 (sandbox next_step rows), 13 H1/H4 notes (F-1, R-04), 14 (+codes)
specs/parser-check-cp5/spec.md      # Assumptions bullet on the engine check (R-02)
specs/parser-check-cp3/contracts/artifact.md   # additive section 11: spine, sandbox, sandbox/ files, outcome and assertion keys

tests/
├── fakes/hc_fake.py, fakes/generate_fake.py, fakes/*.cmd   # NEW -- scriptable fakes (UTF-16LE stdout, delays, crashes)
├── test_sandbox_script.py          # Windows-only: contracts/hcparse.md section 7 invariants, run against the real ps1
├── test_sandbox_discovery.py       # FR-001..FR-004: 4 sources + recorded source, identity, cannot-start, SDK-less listing
├── test_sandbox_versions.py        # FR-005: three versions, skew is a warning, never compared to a floor
├── test_sandbox_engine.py          # FR-036: stream read, fail safe, no LCM import, runs before the copy
├── test_sandbox_workdir.py         # FR-008/011/012: allowlist, no lock, free space, every terminal path, sweep
├── test_sandbox_cache.py           # FR-024/025/026: key, lock, prune, invalidate, in-use protection, -ConfigOut confinement
├── test_sandbox_store.py           # FR-028/029/030: names, no overwrite, origin, predates advisory, seed exclusions
├── test_sandbox_hc_output.py       # FR-016..FR-019: blocks, columns (astral chars), counters, unreadable, -1
├── test_sandbox_classify.py        # FR-031..FR-033: the four-way table, now_parses, bucket mapping
├── test_sandbox_client.py          # FR-020/035: streaming, timeout, cancel, per-run client, not_reached
├── test_sandbox_handler.py         # FR-007/034/041/044: check order with boom-stubs, responses, next_step, labels
├── test_sandbox_lifecycles.py      # SC-007: no cache op changes sandbox/corpus bytes; AST: deleters guard their roots
├── test_sandbox_no_project_writes.py  # FR-042/043: project-folder hash identical; every root refused inside a project
├── test_parse_log_sections.py      # EXISTS -- sandbox runs filled; in-process byte-identical (FR-038)
├── test_parse_diff.py              # EXISTS -- + cross-spine comparison, assertion buckets, staleness either-run
├── test_parser_health_block.py     # EXISTS -- additive keys, the FR-006 flip, the nonexistent-tool example swapped
├── test_cp1_boundary.py            # EXISTS -- R-04 narrowing, + the never--i/-s/-o pin
├── test_parse_no_project_writes.py / test_parse_no_edit_blocking.py   # EXIST -- + server/sandbox/*.py
├── test_mcp_tools.py, test_response_contract.py, test_parser_error_models.py, make_golden.py   # EXIST -- counts, rows, goldens
└── test_parse_live_cp5.py          # requires_flex; L-1..L-7, S1..S13
```

**Structure decision.** The policy lives in a sibling package, `server/sandbox/`, not inside
`parse/`. The reason is that `parse/` carries the in-process spine's standing structural proofs. The
sandbox's risks, disk and subprocess, get their own module boundary and their own tests. Only the
seams join the existing machinery:
- the client role;
- two `RunMeta` fields;
- the log and diff readers.

The script goes to `src/flextoolsmcp/scripts/`, as the parent spec (5.3) placed it. It is resolved
at run time with `Path(__file__).parent`, the `file_utils.get_bundled_templates_dir` convention.

---

## Implementation phases

These are ordered by dependency and risk, and each phase names its exit condition. Phases 2-7 are
entirely offline, so they are **not** blocked on M-1.

### Phase 1 -- Contract and surface first (FR-007, FR-009, FR-034; M-2)

- The detail models, `docs/TOOL-CONTRACT.md` rows, golden fixtures and the CHANGELOG paragraph.
- `ParseSandboxInput`, the ToolDef and the dispatch route, with the handler stubbed to refuse.
- The USAGE.md rows, including `flextools_parse_cancel`.
- The CP5 field-order test block, which parses `contracts/tools.md` section 4.

*Exit*: the contract tests are green at the new count, and `validate_integrity.py server` is clean.

### Phase 2 -- Discovery and health (US1; FR-001..FR-006; R-03, R-04)

- `parser_probe.py`: the four sources with a recorded source, the `hc -h` probe (UTF-16 stdout,
  UTF-8 stderr, closed stdin, 5 s), memoisation, and `FileVersion` reads.
- The health keys, advisories and `next_step` rows.
- The CP1 test narrowing and its pin.

*Exit*: every discovery and health test is green, `TestIntegrationWindowsFieldWorksNoHcTool` is
green on this machine, and S1 is observable here now.

### Phase 3 -- The script (FR-013, FR-014, FR-020..FR-024; contracts/hcparse.md)

- The fakes, written **first**.
- `hcparse.ps1`: the three modes, the allowlist copy, UTF-16 decoding, flushed streaming, the
  timeout with a tree kill, `dispatch.json` and `run.json`, the `-ConfigOut` refusal, and `finally`.
- Package data. The root copy deleted.

*Exit*: `test_sandbox_script.py` is green on Windows. Every invariant in contracts/hcparse.md
section 7 is exercised.

### Phase 4 -- Paths, workdir, engine, cache (FR-008, FR-011, FR-012, FR-024..FR-026, FR-036, FR-042)

- `paths.py`, `workdir.py` (with the shared `disk_space_ok`), `engine.py` and `cache.py`.
- The invalidation call sites: the filing observer, and `run_module` (guarded and lazy).

*Exit*:
- the cache and workdir tests are green;
- `test_issue55_write_safety_ladder.py` and the `run_module` suites pass **unmodified**;
- the backup tests pass unmodified.

### Phase 5 -- Output parsing, classification, the client (US2, US4; FR-015..FR-019, FR-027, FR-031..FR-033, FR-035)

- `hc_output.py` and `classify.py`, written test-first from source-derived fixtures of hc's exact
  output (research F-3..F-8).
- `client.py` and the runner branch. The `parser_timeout` failure path.
- The `RunMeta` fields.

*Exit*: the client tests drive a real `_execute_run` against the fakes: stream, timeout, cancel,
crash, and two concurrent jobs.

### Phase 6 -- Sandboxes, corpora, the handler (US2-US4; FR-028..FR-030, FR-034, FR-037, FR-040, FR-041, FR-044)

- `store.py`.
- `handle_flextools_parse_sandbox`, following the check order of contracts/tools.md section 3,
  with boom-stubs.
- Responses, advisories, labels, `next_step`.

*Exit*: the handler, store and lifecycle tests are green.

### Phase 7 -- Consumers and corrections (US5; FR-038, FR-039)

- `parse_log` becomes spine-aware.
- The diff `comparison` block, assertion buckets and the either-run staleness rule. The signature
  mode is forced for cross-spine pairs.
- Parent-spec edits: 10.2, 13 and 14.
- The CP5 spec Assumptions fix (R-02).
- CP3 `artifact.md` section 11.

*Exit*: the log and diff tests are green, and in-process log responses are byte-identical.

### Phase 8 -- Live verification (FR-045; quickstart L-1..L-7, S1..S13)

**Blocked on M-1.**
- S1 and L-5's "before" half can run now, on this machine.
- Everything else waits for a working `hc`.
- The L-answers are folded back into code: the allowlist, the leading-dash rule, the BOM, the
  timeout default, the runtime matcher.

*Exit*: 13 evidence files exist, each carrying the three versions, and the full suite is green
(SC-010). **With no `hc` and no human, this phase stops as `needs_human`.**

---

## Test strategy

The `lex-qc` plan gate asks for coverage that is *scheduled*, not merely asserted. Every FR has a
row, and each proof names the wrong implementation it catches.

| Requirement | Proof (the wrong implementation fails) | Where |
|---|---|---|
| FR-001 four sources, source recorded | each source in isolation finds hc and records `source`. `.dotnet\tools\hc.exe` is found with PATH lacking it (US1 S2). The override does not fall through when missing | `test_sandbox_discovery.py` |
| FR-002 no hard-coded FW folder | an AST/text scan of `hcparse.ps1` finds no `Program Files` or `LOCALAPPDATA` literal; the argv always carries `-HcPath` / `-GenerateHCConfigPath` | `test_sandbox_script.py` |
| FR-003 identity | a fake `hc` printing other usage text gives `not_hermitcrab`, `found=False` | `test_sandbox_discovery.py` |
| FR-004 absent vs cannot start | a fake host-failure stderr gives `found=True, starts=False, signal=runtime_missing`, a reason naming the runtime, `status=unavailable`. SDK-less `dotnet tool list` failure plus a direct hit gives found | `test_sandbox_discovery.py`, `test_parser_health_block.py` |
| FR-005 three versions, skew is a warning | all three reported; skewed fixtures give the advisory and `ready`; **extended no-floor test**: an absurd version still reports `ready` | `test_sandbox_versions.py`, `test_parser_probe.py` |
| FR-006 naming rule | `ready` names the tool with usable `args`; each `unavailable` variant never names it; the swapped nonexistent-tool sweep still catches a fake name | `test_parser_health_block.py` |
| FR-007 refusal before any copy | missing or non-starting hc gives `parser_tool_missing` (fields in order), `install_hint.startswith(<command>)` plus one sentence; the `work/` root is unchanged (boom-stub on `workdir.create`) | `test_sandbox_handler.py` |
| FR-008 minimal copy | a fake generator lists its folder: only the allowlist, no `*.lock`, `.hg` or `LinkedFiles`; the copy root is outside the project | `test_sandbox_script.py`, `test_sandbox_workdir.py` |
| FR-009 success judged from output | five fixtures: help-exit-0 (no `Writing completed.`), locked, migration, crash, empty config. Each gives `parser_config_failed` with fields in order and the log captured whole. An exit-code-only judge passes the help fixture and so fails the test | `test_sandbox_cache.py` |
| FR-010 load errors itemised, not refused | a config written with 3 load-error lines gives `load_error_count=3`, the kinds tagged, the run proceeds, the advisory present, and they are carried on a **warm** run too | `test_sandbox_cache.py`, `test_sandbox_handler.py` |
| FR-011 copy always deleted | a parametrised terminal path (success, generator fail, hc load fail, timeout, cancel, exception in the client) leaves `work/` empty. Tree-kill-skips-finally: the client's own delete. The startup sweep removes a marked orphan and ignores unmarked dirs | `test_sandbox_workdir.py`, `test_sandbox_client.py` |
| FR-012 2x free space | a patched `disk_usage` below 2x the **allowlist** size gives the refusal with `needed_bytes` and `free_bytes`, and no directory created; the backup tests stay unmodified | `test_sandbox_workdir.py` |
| FR-013 quoting, not-expressible | apostrophe goes to `"..."`; `"` goes to `'...'`; both gives `sent:false`; the tab/CR/LF cases; a leading-`-` word is flagged | `test_sandbox_script.py` |
| FR-014 H11 verbatim | the `-Words "a,b c"` split; a UTF-8 no-BOM script (bytes checked); a non-Latin word file round-trips | `test_sandbox_script.py` |
| FR-015 ordering | NFC duplicates merged; the count order then alphabetical; `limit` applied after ordering; `truncated_by_limit` recorded | `test_sandbox_handler.py` |
| FR-016 not from exit code | exit 0 with failing words classified per word; -1 with `Load Error:` gives a failed run with the message and zero results | `test_sandbox_hc_output.py`, `test_sandbox_client.py` |
| FR-017 right counters, disagreement reported | parse reads `stats -p`, test reads `stats -t`; a mismatch fixture gives `counter_divergences` and neither side overwritten | `test_sandbox_hc_output.py` |
| FR-018 exactly one result per word | every outcome enum from fixtures; a crash mid-list gives `error_no_output` plus `not_reached`, **never** `not_parsed`; a count invariant over randomised lists | `test_sandbox_hc_output.py`, `test_sandbox_client.py` |
| FR-019 unreadable columns | an empty form, a space in a gloss and an astral character: the first two are `readable:false` with `raw` kept; the astral case **reads correctly** (UTF-16 widths). A code-point-width parser fails it | `test_sandbox_hc_output.py` |
| FR-020 / SC-008 timeout | a fake that sleeps on word 41 of 100 gives `parser_timeout` (fields in order), `words_completed=40`, the in-flight word named, 40 lines in `results.jsonl`, and the tree killed | `test_sandbox_client.py`, `test_sandbox_script.py` |
| FR-021 ASCII console | the script's captured stdout is ASCII; `stderr_tail` escapes non-ASCII | `test_sandbox_script.py`, `test_sandbox_cache.py` |
| FR-022 packaged, invoked safely | the wheel contains `scripts/hcparse.ps1`; the argv is a list starting with the exact invocation; no `-Command` or `Invoke-Expression` anywhere | `test_sandbox_script.py` |
| FR-023 `run.json` folded, no prose scraping | the meta is built from `run.json` and flushed files only; an AST check that the client never reads the script's stdout for data | `test_sandbox_client.py` |
| FR-024 version constant keys the cache | exactly one `HCPARSE_VERSION` match; bumping it changes the key | `test_sandbox_cache.py` |
| FR-025 / SC-007 three lifecycles | prune, invalidate and rebuild leave sandbox and corpus bytes identical; an AST check that every deleter guards its root; an in-use entry survives prune | `test_sandbox_lifecycles.py`, `test_sandbox_cache.py` |
| FR-026 invalidation, `-ConfigOut` confinement | a CP4 `after_terminal` and a successful write-enabled `run_module` each invalidate; a read-only `run_module` does not; an AST check that `-ConfigOut` is passed only by `cache.build_entry`; the script exits 3 under `sandboxes` | `test_sandbox_cache.py`, `test_sandbox_script.py` |
| FR-027 expectation check | each of `\| : \ ' "` and whitespace, and an empty parse, gives an `error: not_expressible` line; the rest of the corpus runs; a hanging escape can never be emitted (the dispatch never contains `\`) | `test_sandbox_script.py`, `test_sandbox_classify.py` |
| FR-028 sandbox creation | a path is returned; `origin.json` is recorded; a second create is refused and the **first file is byte-identical**; `..`, separators, `CON`, empty and too long are refused | `test_sandbox_store.py` |
| FR-029 predates advisory | after a project stat change, the advisory is present and the sandbox bytes are unchanged | `test_sandbox_store.py` |
| FR-030 seeding | every parsed word keeps its exact parses; not-parsed becomes `[]`; other outcomes are excluded and listed; a non-sandbox or incomplete run is refused | `test_sandbox_store.py` |
| FR-031 / FR-033 / SC-005 classification | the four-way table from F-8 fixtures; `[]`-then-parses gives `new_ambiguity` + `now_parses`; never "fixed" (text scan) | `test_sandbox_classify.py` |
| FR-032 buckets | regression goes to broken; new_ambiguity and changed go to changed; new_ambiguity is never unchanged | `test_sandbox_classify.py`, `test_parse_diff.py` |
| FR-034 registration | name, `READ_ONLY_SAFE`, and the first line pinned; the description carries the three phrases | `test_mcp_tools.py`, `test_sandbox_handler.py` |
| FR-035 one execution path | cancel via `flextools_parse_cancel` kills the tree; status polls; a fast-path inline result; the client is not pooled (two concurrent jobs get distinct clients and copies) | `test_sandbox_client.py` |
| FR-036 engine check first, no open | an XAmple `.fwdata` fixture gives the refusal before the copy (boom-stub); an absent or unparseable value refuses (fail safe); no `flexicon` or LCM import on the path (`sys.modules` check) | `test_sandbox_engine.py` |
| FR-037 record format, additive | a sandbox run reads through `read_meta` with `spine` and `sandbox` intact **after a stage change** (the F-12 trap); pre-CP5 fixtures read as `in_process` | `test_parse_record.py` (EXISTS, extended) |
| FR-038 log sections | a sandbox run gives real content for all three sections, including a warm run's reuse line; in-process responses are byte-identical to today's golden; an empty file gives `_empty_note` | `test_parse_log_sections.py` |
| FR-039 cross-spine diff | the diff runs, `comparison.note` names the two engines, and the form-only comparison is disclosed | `test_parse_diff.py` |
| FR-040 staleness | `open_shared`, `open_exclusive` and `held_by_other` each give `shared_mode_unverifiable`; the diff downgrades when either run carries it | `test_sandbox_handler.py`, `test_parse_diff.py` |
| FR-041 `next_step` + `est_cost` | present on every response variant; failure, timeout and load errors point to `flextools_grammar_health` | `test_sandbox_handler.py` |
| FR-042 nothing in a project folder | every root and override set inside a fake project folder is refused; the copy root is checked | `test_sandbox_no_project_writes.py` |
| FR-043 byte-identical | a fake project folder is hashed before and after a full fake run and is identical; `sandbox/` joins the no-write scans | `test_sandbox_no_project_writes.py`, `test_parse_no_project_writes.py` |
| FR-044 data not instructions | words and XML carrying instruction-like text are echoed inside data fields only; the envelope text is fixed | `test_sandbox_handler.py` |
| FR-045 live | quickstart S1-S13, L-1-L-7 | `test_parse_live_cp5.py` (M-1) |
| SC-001 no copy remains; project byte-identical | FR-011's parametrised terminal paths, plus FR-043's before-and-after hash, asserted together in one test per path | `test_sandbox_workdir.py`, `test_sandbox_no_project_writes.py`, every live scenario |
| SC-002 health names the right cause | FR-004's no-hc and cannot-start fixtures, and FR-006's never-named sweep | `test_parser_health_block.py`, live S1 and S2 |
| SC-003 parity with Try A Word | **Live only** (L-6). It is fully provable only if M-1 yields a version-matched `hc`. On the no-SDK 3.7.x route it is recorded as *partially verified (version-skewed)*, never as passed | `test_parse_live_cp5.py` |
| SC-004 zero silent losses | FR-018's randomised count invariant (words sent == results) | `test_sandbox_hc_output.py`, `test_sandbox_client.py` |
| SC-009 log sections never empty | FR-038's four-run matrix (success, load errors, timeout, broken sandbox) | `test_parse_log_sections.py` |
| SC-006 warm is at least 2x faster | the fake generator is slow and the second run skips it (offline); the real timing comes from S5 | `test_sandbox_cache.py`, live S5 |
| SC-010 no regressions | the full suite, the boundary tests and the error-model field-order tests | CI |

**Wrong-implementation tripwires.** These tests are written so that the tempting implementation
fails, not merely disagrees:
- **FR-009's help-exit-0 fixture**: an exit-code judge passes it, and so fails the test.
- **FR-019's astral-character column**: a code-point width misreads it.
- **FR-018's crash mid-list**: "no output means not parsed" is exactly the error.
- **F-12's stage-change round-trip**: an undeclared meta key vanishes.
- **FR-011's tree-kill path**: relying on the script's `finally` leaks a copy.
- **FR-028's create-twice**: an `open(..., "w")` overwrites the file.
- **F-5 never emitted**: a morph without `:` would leak into the next test.

**Pattern-audit obligations.** Each shaped class gets a sweep, not a point fix. Findings go in the
commit body, per the constitution.

1. **Trusting a subprocess exit code** (H4 and FR-009's shape). Sweep every `subprocess.run`,
   `run_script_async` and `create_subprocess_exec` consumer in `src/` for "returncode == 0 means
   success" where the program's contract says otherwise.
2. **Cleanup on the happy path only** (H6's shape). Sweep `mkdtemp`, `TemporaryDirectory`,
   `NamedTemporaryFile(delete=False)` and temp-dir `mkdir` for deletion on every path, including a
   tree kill.
3. **A verdict set that omits a member** (F-16). Sweep every consumer of `ProjectAccess.verdict`
   for sets that list some of `open_shared`, `open_exclusive` and `held_by_other` but not all. For
   each, record whether the omission is intended. This is where R-13's in-process question gets
   answered.
4. **An implicit subprocess encoding** (F-1's shape). Sweep `text=True` without `encoding=`, and
   decodes without a declared codec. `_find_hc_via_dotnet_tool_list` is a known instance, and this
   change fixes it.
5. **A typed reader that silently drops keys a writer adds** (F-12). Sweep other `read_*` or
   `from_dict` helpers that filter to declared fields where more than one writer exists.

**Live verification.** It is mandatory, read-path, with a byte-identity hash on every scenario, and
blocked on M-1 (quickstart).

---

## Complexity Tracking

| Violation / complexity | Why needed | Simpler alternative rejected because |
|---|---|---|
| A new `server/sandbox/` package of 9 modules | The sandbox's risks (disk, subprocess) and its three lifecycles need their own boundary and tests. `parse/` carries the in-process spine's standing no-write proofs | Folding it into `parse/` mixes subprocess and file-deletion code into modules whose structural tests assume neither |
| **CP1 invariant narrowed** (R-04): discovery may run `hc -h` | FR-003 and FR-004 need an observed start. `-h` exits before any config is read (F-2) | A file-only probe cannot tell "not HermitCrab" or "cannot start" apart from "ready". Mitigation: one permitted argv shape, pinned, plus a never-`-i`/`-s`/`-o` test |
| The script is invoked twice per cold job (Generate, then Parse/Test) | The cache lock must cover generation only (R-01) | One invocation holds the lock for the whole parse, and a second job would wait hours |
| `run.json` per-word entries record dispatch, not interpretation (R-01) | One parser of hc's format (Principle VI); per-word streaming needs Python to read the live stream | A PowerShell classifier duplicates the Python one, or loses streaming. Flagged for the maintainer at the plan gate |
| A per-run client outside `WorkerPool` | The pool keys by `(project, role)` (F-13), and concurrent sandbox jobs need separate copies | Keying the pool by run id changes pooling for every role |
| `parse_sandbox_refused` (M-2) | Six refusal kinds have no code among the 34 (R-16) | `runtime_error` violates Principle V; six codes bloat the surface for one tool |

---

## Risks

| Risk | Handling |
|---|---|
| **No working `hc` for live verification** (R-15) | M-1. The offline phases proceed. Phase 8 is `needs_human` until a route is chosen |
| The allowlist copy is not enough for `GenerateHCConfig` (L-1) | It fails loudly as `parser_config_failed`, never as a grammar problem. L-1 extends the allowlist, and the free-space measure follows it |
| The UTF-16 decoding is wrong in PowerShell 5.1 (L-3) | The fake emits real UTF-16LE, so an offline test catches the regression class. L-3 confirms the BOM |
| A stream read of a large `.fwdata` is slow | Early exit at the first `MoMorphData`. The result is cached in `key.json` by `(path, size, mtime)`. Measured in S4 |
| Reading `.fwdata` while FLEx saves it gives a spurious XAmple refusal | One retry. The hint names "could not be read" as distinct from "is XAmple". L-7 |
| Cache invalidation raises inside `run_module` | A lazy, guarded import and try/except, logged and never propagated. The ladder suite passes unmodified |
| Windows sharing violations on deletion | Retries, and a recorded `cleanup: failed` with the path, swept next time. Never silent |
| hc and FLEx disagree at matching versions (L-6) | Recorded, never hidden. `results_label` already says these are the sandbox's results |

---

## Open maintainer decisions

| # | Decision | Default taken so planning is not blocked | When it must be settled |
|---|---|---|---|
| **M-1** | How to get a working `hc` for FR-045: (a) install a .NET SDK and .NET 10, then `dotnet tool install` (current `hc`, skewed against 3.8.2), or (b) the no-SDK route: extract the 3.7.x nupkg's `hc.dll` and set `HC_TOOL_PATH` (runs on .NET 8; no matching-version parity for SC-003) | None. It is an outward-facing install, and this session does not perform it | Before Phase 8. **This is a `needs_human` stop** |
| **M-2** | Add `parse_sandbox_refused` (a seventh code beyond the spec's list) for name, existence, corpus, seeding and disk refusals | Add it (count 34 to 36) | Before Phase 1 lands. Overturning it later changes the contract rows |
| **M-3** | FR-023 reading: `run.json` per-word entries record dispatch; Python interprets hc's output (R-01) | Python interprets | Before Phase 3 |
| **M-4** | Q2 and Q3 are still open in the spec (seeding source; skew policy) | The spec's defaults: baseline seeding; warn, never refuse | Before `/speckit.tasks`, or accepted as written |
