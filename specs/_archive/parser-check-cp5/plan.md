# Implementation Plan: parser-check CP5 -- the sandbox spine

**Branch**: `feat/parser-check-cp5`, from `main` at `2772b52`

**Date**: 2026-09-24

**Spec**: [`spec.md`](./spec.md), over [`../parser-check/SPEC.md`](../parser-check/SPEC.md) sections 5.3, 5.5, 6.2, 7, 10, 10.1, 10.2, 13 and 14

**Predecessors**: CP1-CP4 on `main`. Issue #165 is a sequencing dependency only.

**Re-planned 2026-09-24 (see `HANDOFF.md`; `research.md` R-17, decisions D1-D8).** **M-1 is
resolved**, not the way this plan originally assumed: there is no `hc` CLI. Parse and Test run
in-process, in a `--sandbox` mode of the existing parse worker
(`src/flextoolsmcp/server/parse/worker_main.py`), calling FieldWorks' own bundled
`SIL.Machine.Morphology.HermitCrab.dll` directly. Generate mode (the allowlisted copy,
`GenerateHCConfig.exe`, the cache) is unchanged. Every "blocked on M-1" phase gate below is removed;
Phase 8 (live verification) can now run to completion without a maintainer install step. Text
retired by the re-plan is marked "Retired (CP5 re-plan 2026-09-24)" rather than deleted.

**Size**: `oversized`, so this is a full-tier plan. It touches a published contract (one new tool, one or two new codes) across many modules.

**Write path?** **No.** The spine never opens the live project through LCM and never writes a file
in any project folder. The one new write-adjacent behaviour is **cache invalidation** triggered by
existing writes, which deletes only MCP-owned cache files. The constitution's live-LCM *write*
verification therefore does not apply. FR-045's live run is still mandatory. **Updated (CP5 re-plan
2026-09-24): it is no longer blocked on M-1** -- the sandbox worker loads FieldWorks' own bundled
engine, which is already present on any machine with FieldWorks installed, so no external `hc`
install is a precondition for Phase 8.

---

## Summary

**Reworded (CP5 re-plan 2026-09-24).** CP5 packages the maintainer's `hcparse.ps1` for **Generate
mode only** (the allowlisted copy plus `GenerateHCConfig.exe`, cached) behind a new read-only tool,
`flextools_parse_sandbox`, and runs words or a corpus of expected parses **in-process**, in a
`--sandbox` mode of the existing parse worker, calling FieldWorks' own bundled
`SIL.Machine.Morphology.HermitCrab.dll` directly (`XmlLanguageLoader.Load`, `Morpher`, `ParseWord`).
There is no longer a stand-alone `hc` tool anywhere in the design. Users may also copy the export
into a named, user-owned sandbox and edit it freely. The live project is never opened or written,
and, new in the re-plan, the sandbox worker process itself never imports flexicon/LCM and never
touches the project at all (FR-046).

The technical approach splits mechanism from policy, **reworded from research R-01**:
- **The PowerShell script**, now Generate-mode only, copies, generates, and always deletes the copy.
  ~~quotes, runs `hc` under a timeout, streams its output to flushed files~~: retired, that was
  Parse/Test's job and Parse/Test no longer go through the script.
- **The sandbox worker process** (new) loads the exported configuration and the bundled HermitCrab
  engine, applies the project's parser parameters (D3/FR-047), and returns structured per-word
  analyses (including the `guessed` flag, D5/FR-048) over the worker's existing JSON-lines protocol.
  It runs under a timeout and is killed on timeout or cancellation, same as before, but there is no
  separate `hc` process beneath it to also kill.
- **Python** owns everything else: discovery (now: locating the bundled DLL, not `hc`), the engine
  check, the cache and its three lifecycles, classification, and the sandbox-mode message refusals
  (D1/FR-049).
- **The job model is reused.** A per-run `SandboxClient` implements the worker-client interface, so
  status, the fast path, cancellation, retention, logs and diff come without a second execution
  path (R-07). Unaffected by the re-plan.

Reading the `hc` and `GenerateHCConfig` sources turned up facts the spec does not state, and each
is designed for (research F-1..F-17; **most now apply only to Generate mode, or to the engine
itself rather than an `hc` CLI wrapping it -- see research.md's per-fact notes**). What matters most
now:
- ~~`hc`'s console output is **UTF-16LE** (F-1).~~ Moot for Parse/Test: the worker returns structured
  .NET objects, not printed text. Still true of `hc` itself as a fact about the tool, but no code
  path decodes it any more.
- ~~A malformed `test` expectation **leaks into the next test** (F-5).~~ Moot: there is no `test`
  command; corpus comparison is a Python-side structural comparison with no shared mutable state
  between assertions.
- The run record **silently drops** undeclared meta keys (F-12). **Unaffected** -- still a live
  hazard for the new `spine`, `sandbox`, `parser_parameters`, `parameters_applied`,
  `parameters_source` fields.
- ~~FR-003's identity probe collides with a **standing CP1 invariant** (F-15), which is narrowed
  rather than dropped (R-04).~~ **Superseded (D2).** FR-003 (the `hc -h` identity probe) is retired
  outright, since there is no `hc` to probe. The CP1 boundary instead gains a narrower,
  differently-shaped exception: `Morpher` and `XmlLanguageLoader.Load` join a pinned
  `CP5_SANDBOX_ENGINE_ALLOWLIST` scoped to `worker_main.py`'s `--sandbox` mode only (see research.md
  R-17, D2).

No new language or dependency is added. `FileVersion` is read with `ctypes` against the Win32
version API, which is Windows-only by design (Principle VII). Pythonnet's `netfx` mode plus an
`AssemblyResolve` handler (already proven live in `reference/hc_fw_prototype.py`) is how the sandbox
worker loads the engine and its `SIL.Core`-version-mismatched dependencies.

---

## Scope fence

| Not in this slice | Where | Why |
|---|---|---|
| Expectations from human-approved analyses | deferred (Q2 default) | Seeding from a baseline run only (FR-030) |
| ~~Refusing a skewed `hc` version~~ **Moot (D7, CP5 re-plan)** | n/a | There is no independently-installed engine to be skewed against any more; the skew warning is removed, not just never triggered (Q3 moot, FR-005) |
| `hc` tracing (`tracing on`) | follow-up | Not in the spec. `Morpher`/`TraceManager` trace output would need its own reader and size cap if this is ever picked up in-process |
| Word lists from a CP3 text scope | follow-up | Resolving a scope opens the live project through the worker (the lock, per memory note `non-shared-projects-single-opener`). CP5 takes explicit words or a word file |
| Deleting sandboxes or corpora through the tool | out | They are user-owned. `list` gives paths and the user deletes with ordinary tools |
| ~~Installing `hc`, an SDK or a runtime~~ **Moot (CP5 re-plan)** | n/a | Nothing separate is installed. The analogous out-of-scope item: repairing/reinstalling FieldWorks is named in hints, never performed |
| Contract prose, telemetry, user docs | CP6 (#167) | Only contract rows and the CHANGELOG paragraph land here |
| Widening `held_by_other` staleness to in-process diffs | pattern audit, sweep 3 | R-13 keeps CP3's verdicts unchanged |
| ~~replicating Try A Word's circumfix doubling and `FormID==0` skipping from the exported `Properties`, deferred as a named gap~~ **Reworded (D4 reversed, maintainer correction 2026-09-24): in scope, not deferred** | in this slice | These are FLEx's own display rules (`HCParser.GetMorphs`), not bugs; CP5 replicates them via a validated `lcm-ids.json` id map (spec.md FR-050, research.md D4) rather than naming them a permanent gap |
| **New**: per-word engine reopen / reload discipline for the sandbox backend | out (D8, tracks #223) | #223's per-word reopen question is about `_RealBackend`; the sandbox backend deliberately keeps one `Morpher` per run (FR-049/D1) and does not reopen per word |

---

## Technical Context

| | |
|---|---|
| **Language/Version** | Python 3.11+. Windows PowerShell **5.1** for the script, **Generate mode only** (no PowerShell 7 syntax) |
| **Primary Dependencies** (**reworded, CP5 re-plan 2026-09-24**) | The FieldWorks-bundled `SIL.Machine.Morphology.HermitCrab.dll` (loaded in-process by the sandbox worker via pythonnet `netfx`, not discovered or installed separately -- there is no `hc`); `GenerateHCConfig.exe` from FieldWorks 9. Internal: `pydantic` v2 detail models, the CP2b-CP4 job runner and run record, the existing worker JSON-lines protocol |
| **Storage** | `~/.flextoolsmcp/parse/{config-cache,sandboxes,corpora,work}/` (override `FLEXTOOLSMCP_PARSE_SANDBOX_DIR`). Sandbox files under each run's `sandbox/` directory. **Nothing in a project folder** (FR-042). Unaffected by the re-plan |
| **Testing** (**reworded**) | `pytest`, offline by default. Generate-mode script tests run PowerShell with a **fake generator**. Sandbox-worker tests run the `--sandbox` mode against the real FieldWorks-bundled DLL where available, or are marked Windows-only / `requires_flex` where a real engine load is needed. ~~fake `hc`~~ is retired; there is no `hc` to fake. `requires_flex` live tests are gated by `FLEXLIBS_REQUIRE_LIVE` |
| **Target Platform** | Windows with FieldWorks 9 |
| **Constraints** (**reworded**) | Contract stays `tool-responses/1.0`. The live project is never opened through LCM by this spine, and the sandbox worker process never imports flexicon/LCM at all (FR-046). Console output is ASCII, for Generate mode. The CP1-CP4 standing tests stay green, apart from D2's documented, narrower carve-out (`CP5_SANDBOX_ENGINE_ALLOWLIST`, replacing the originally-planned R-04 narrowing) |
| **Scale/Scope** | 1 new tool, 1 new code (2 with M-2), 1 new package of 9 modules, 1 packaged script (Generate mode only), a `--sandbox` mode added to the existing worker, extensions to existing modules, and new test files |

---

## Constitution Check

*GATE: must pass before Phase 0 research, and is re-checked after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Safety-First Write Path** (NON-NEGOTIABLE) | **PASS / mostly N/A.** No database write exists on this spine, and it opens no LCM project. Enforcement is structural: `sandbox/` is added to the no-writes scans (`test_parse_no_project_writes.py`, `test_parse_no_edit_blocking.py`), and the inverse confinement test (`test_filing_write_confinement.py`) already covers all of `src/`. The copy happens outside project folders (FR-042) and is always deleted (FR-011). Cache invalidation on write completion **follows** the existing ladder and never gates or alters it, so an import failure there cannot break `run_module` (R-12). **Reworded (CP5 re-plan):** the sandbox worker process itself is a *stronger* boundary than before -- it never imports flexicon/LCM at all (FR-046), provable via its `assemblies` message and `sys.modules`. Stated plainly: these are safety properties, not a security boundary. ~~A user can point `HC_TOOL_PATH` anywhere~~: moot, there is no `HC_TOOL_PATH` any more; the DLL path comes only from the MCP's own FieldWorks resolution |
| **II. Discovery Over Memory** | **PASS / N/A.** No generated-module surface changes. `hc` and generator behaviour are taken from source (research F-table; **most of the `hc`-CLI facts are now historical/engine-level context rather than load-bearing for Parse/Test**, per research.md's per-fact notes), and unknowns are **[LIVE]**, not assumed |
| **III. Self-Contained, Regenerable Extraction** | **PASS / N/A.** No index or extractor change. pyflexicon is untouched, so memory note `release-order-flexicon-first` does not apply |
| **IV. Append-Only Versioned Contracts** | **PASS.** Additive throughout: one tool; `parser_config_failed` (plus `parse_sandbox_refused`, pending M-2); `parser_job_failed` (**new**, D7); additive `RunMeta` fields (`spine`, `sandbox`, and **new**: `parser_parameters`, `parameters_applied`, `parameters_source`); additive health keys; additive `results.jsonl` keys (**new**: per-morph `guessed`). The existing `parser_tool_missing` and `parser_timeout` shapes are unchanged, though `parser_tool_missing`'s `component` values and `install_hint` text change (D7). **No version floor**, and there is no longer a version to be skewed at all (Q3 moot, D7): the skew-warning test class is retired rather than extended. One CHANGELOG "Tool contract" paragraph |
| **V. Errors That Teach** | **PASS.** Every refusal names its next step: ~~the install command plus prerequisites; the runtime to install~~ **retired (D7)**, now "repair FieldWorks"; the static grammar scan after a generation failure, timeout or load errors (FR-041); the space needed against the space free. Health tells "absent" apart from a load failure that is deferred to run time, not discovered by health (D7, replaces "absent" vs "cannot start", FR-004). One code path writes both the human log (`generate-config.log`, and now the sandbox worker's own captured stdout/stderr) and the structured record (`run.json` folded into `meta.json` for Generate mode; the worker's JSON-lines messages folded directly for Parse/Test) |
| **VI. One Module, One Source of Truth** | **PASS, with one justified tension.** Each rule has exactly one owner: **Generate-mode** copying/quoting lives in the script; the engine call, parameter application (D3) and per-morph extraction (D4/D5) live in the sandbox worker; classification lives in Python. The job runner is reused, not paralleled (FR-035). **Tension**: two copies of the 2x free-space rule (backup and sandbox) measure different things. Resolution: extract `backup._space_skip_reason`'s rule into a shared `disk_space_ok(path, needed_bytes)` and have both callers use it. That is a small refactor, pinned by the existing backup tests passing unmodified |
| **VII. Windows-First** | **PASS.** Windows PowerShell 5.1 (Generate mode), Win32 `FileVersion`, process-tree kill for the sandbox worker. The script tests are marked Windows-only and skip on the Linux smoke job. Console output is ASCII for Generate mode (FR-021). ~~**Subprocess boundaries are encoding-explicit**: UTF-16LE from `hc` (F-1)~~: **moot for Parse/Test** -- the worker exchanges structured JSON-lines messages, already UTF-8/Unicode-safe by the existing worker protocol's own design, so this principle's concern is satisfied by reuse rather than a new encoding rule |

**Quality gates.**
- *Pattern audit*: five sweeps, listed below.
- *Live verification*: mandatory for FR-045. It is read-path only, and a reference project is
  allowed, but every scenario still takes a byte-identity hash. **Updated (CP5 re-plan 2026-09-24):
  no longer blocked on M-1** -- the sandbox worker loads FieldWorks' own bundled engine, present on
  any FieldWorks-installed machine.
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
- ~~The CP1 narrowing (R-04) is not a constitution matter, but it does change a standing test. It is
  pinned by a new test that fails if discovery ever passes `-i`, `-s` or `-o`.~~ **Superseded (D2,
  CP5 re-plan 2026-09-24).** R-04's `hc -h` carve-out is retired along with `hc` discovery. The CP1
  boundary instead gains `CP5_SANDBOX_ENGINE_ALLOWLIST`, a narrower, differently-shaped exception
  scoped to `Morpher` / `XmlLanguageLoader.Load` inside `worker_main.py`'s `--sandbox` mode only,
  pinned by its own dedicated test rather than a never-`-i`/`-s`/`-o` argv pin.

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
│   └── hcparse.md       # script parameters, exit codes, run.json, invariants (dispatch.json is
│                         #   retired -- section 4 -- kept only as a record of the old spine)
├── checklists/requirements.md
├── reviews/             # cycle1-domain.md; cycle1-qc.md; plan-gate QC lands here
├── evidence/            # live artifacts (**updated, CP5 re-plan: no longer blocked on M-1**)
└── tasks.md             # /speckit.tasks -- NOT created here
```

### Source Code

**Reworded (CP5 re-plan 2026-09-24).** The module map below replaces the original: `hc_output.py`
and `script.py`'s Parse/Test responsibilities move into the worker; `parser_probe.py`'s `hc`
discovery is replaced by DLL-presence discovery; a new `_SandboxBackend` lands in the existing
worker module rather than a new client-side subprocess wrapper.

```text
src/flextoolsmcp/
├── scripts/
│   └── hcparse.ps1                 # NEW -- packaged, hardened, Generate mode only (contracts/hcparse.md). Replaces the root copy
├── server/
│   ├── parse/
│   │   ├── worker_main.py          # + `--sandbox` mode, `_SandboxBackend`: AssemblyResolve handler, XmlLanguageLoader.Load, Morpher, ParseWord, per-morph MorphInfo-equivalent extraction (D5), Try A Word shaping rules a-d against `--id-map` (D4 reversed, FR-050), parameter application (D3/FR-047), D1's message refusals and neutral hooks
│   │   ├── record.py               # RunMeta + spine, sandbox, parser_parameters, parameters_applied, parameters_source (F-12); _child writes for sandbox/ files
│   │   ├── runner.py               # start_run: SANDBOX_ROLE builds a per-run client, not a pooled one (F-13); parser_timeout failure
│   │   ├── diff.py                 # comparison block (R-14); either-run staleness downgrade (R-13); assertion buckets
│   │   └── signature.py            # force RENDERED_FALLBACK for cross-spine pairs (R-14)
│   ├── sandbox/                    # NEW package -- the sandbox spine's server-side policy (Generate mode + spawn control; the engine itself lives in worker_main.py)
│   │   ├── __init__.py
│   │   ├── paths.py                # root + env override, per-project dirs, name validation, assert_outside_project (R-11)
│   │   ├── engine.py               # stream-read ActiveParser from the live .fwdata, no LCM (R-02); runs before any copy AND before the sandbox worker is spawned (D6)
│   │   ├── workdir.py              # allowlist measure, free-space check, marker, retrying delete, startup sweep (R-11)
│   │   ├── cache.py                # key, per-key asyncio lock, build via -Mode Generate, LRU prune, invalidate; key.json carries hc_parameters (D3) and the `lcm-ids.json` sidecar path (D4 reversed, FR-050), neither part of the key
│   │   ├── script.py               # HCPARSE_VERSION reader; argv builder (never a string) for Generate mode only; run.json/dispatch.json loaders
│   │   ├── classify.py             # parse outcomes; assertion classification (direct structural comparison, not hc's sections); diff-bucket mapping (R-10)
│   │   └── store.py                # sandbox create/list/origin; corpus seed/load/validate (data-model 4, 5)
│   ├── handlers/
│   │   ├── diagnostic_health.py    # sandbox component keys (DLL FileVersion, not hc versions), advisories, next_step rows; FR-006 rule (contracts 6)
│   │   ├── parse.py                # + handle_flextools_parse_sandbox; parse_log spine-aware (FR-038); diff comparison
│   │   └── execution.py            # + guarded, lazy cache invalidation after a successful write-enabled run_module (R-12)
│   ├── filing/observer.py          # after_terminal: + invalidate the sandbox cache for the project (FR-026)
│   ├── backup.py                   # _space_skip_reason's rule extracted to a shared disk_space_ok (Principle VI)
│   ├── models.py                   # + ParseSandboxInput
│   ├── response_models.py          # + ParserConfigFailedDetail (+ ParseSandboxRefusedDetail, M-2; + ParserJobFailedDetail/engine_unavailable, D7; + ParserJobFailedDetail/id_map_invalid, D4 reversed/FR-050); AnyDetail; docstring tally
│   ├── tool_definitions.py         # + flextools_parse_sandbox ToolDef
│   └── dispatch.py                 # + route (the six touch points of CP4's parse_cancel)
pyproject.toml / MANIFEST.in        # + "scripts/*.ps1" package data
hcparse.ps1 (repo root)             # DELETED (history kept); scripts/ralph/campaign.json references updated
docs/TOOL-CONTRACT.md               # + rows; count 34 -> 35 (36 with M-2; 37 with parser_job_failed, D7)
USAGE.md                            # + flextools_parse_sandbox and flextools_parse_cancel rows (F-17)
CHANGELOG.md                        # one "Tool contract" paragraph + the new tool
specs/parser-check/SPEC.md          # 10.2 (sandbox next_step rows), 13 H1/H4 notes (superseded, D7), 14 (+codes)
specs/parser-check-cp5/spec.md      # Assumptions bullet on the engine check (R-02, updated D6)
specs/parser-check-cp3/contracts/artifact.md   # additive section 11: spine, sandbox, sandbox/ files, outcome and assertion keys, parser_parameters/parameters_applied/parameters_source, guessed

tests/
├── ~~fakes/hc_fake.py, fakes/*.cmd~~ RETIRED -- no `hc` to fake. fakes/generate_fake.py kept for Generate mode
├── test_sandbox_script.py          # Windows-only: contracts/hcparse.md section 7 invariants, run against the real ps1 (Generate mode only)
├── test_sandbox_discovery.py       # FR-001, FR-004, FR-007: DLL presence + FileVersion, no process spawn/load (D7)
├── ~~test_sandbox_versions.py~~ RETIRED -- no skew warning to test (D7); FileVersion reporting folds into test_sandbox_discovery.py
├── test_sandbox_engine.py          # FR-036/D6: stream read, fail safe, no LCM import, runs before the copy AND before the worker spawns
├── test_sandbox_workdir.py         # FR-008/011/012: allowlist, no lock, free space, every terminal path, sweep
├── test_sandbox_cache.py           # FR-024/025/026: key, lock, prune, invalidate, in-use protection, -ConfigOut confinement, hc_parameters excluded from the key
├── test_sandbox_store.py           # FR-028/029/030: names, no overwrite, origin, predates advisory, seed exclusions
├── test_sandbox_worker.py          # NEW, replaces test_sandbox_hc_output.py -- FR-016..FR-020, FR-046..FR-048, FR-050: engine load, ParseWord outcomes, guessed flag, shaping rules a-d against a synthetic id map, parameter application, process isolation
├── test_sandbox_classify.py        # FR-027, FR-031..FR-033: schema validation, the four-way table, now_parses, bucket mapping
├── test_sandbox_client.py          # FR-020/035: streaming, timeout, cancel, per-run client, not_reached
├── test_sandbox_handler.py         # FR-007/034/041/044/049: check order with boom-stubs, responses, next_step, labels, D1 message refusals
├── test_sandbox_lifecycles.py      # SC-007: no cache op changes sandbox/corpus bytes; AST: deleters guard their roots
├── test_sandbox_no_project_writes.py  # FR-042/043/046: project-folder hash identical; every root refused inside a project; no LCM import
├── test_parse_log_sections.py      # EXISTS -- sandbox runs filled; in-process byte-identical (FR-038)
├── test_parse_diff.py              # EXISTS -- + cross-spine comparison, assertion buckets, staleness either-run
├── test_parser_health_block.py     # EXISTS -- additive keys, the FR-006 flip, the nonexistent-tool example swapped for a missing-DLL example
├── test_cp1_boundary.py            # EXISTS -- D2's CP5_SANDBOX_ENGINE_ALLOWLIST pin (replaces the R-04 hc -h narrowing)
├── test_parse_no_project_writes.py / test_parse_no_edit_blocking.py   # EXIST -- + server/sandbox/*.py
├── test_mcp_tools.py, test_response_contract.py, test_parser_error_models.py, make_golden.py   # EXIST -- counts, rows, goldens
└── test_parse_live_cp5.py          # requires_flex; L-1..L-7, S1..S13 (**no longer blocked on M-1**)
```

**Structure decision** (**reworded, CP5 re-plan 2026-09-24**). The server-side policy (paths, the
engine check, the workdir, the cache, classification, sandbox/corpus storage) lives in a sibling
package, `server/sandbox/`, not inside `parse/`. The reason is that `parse/` carries the in-process
spine's standing structural proofs, and Generate mode's risks (disk, a real subprocess) still want
their own module boundary and tests. The engine itself, however, lives inside
`server/parse/worker_main.py` as a `--sandbox` mode and `_SandboxBackend` -- not in `server/sandbox/`
-- because it must reuse the existing `ParseWorker` loop and JSON-lines protocol exactly, and the CP1
boundary tests already pin `worker_main.py` as the one place parser calls are allowed to happen.
Only the seams join the existing machinery:
- the client role;
- the `RunMeta` fields (`spine`, `sandbox`, and the D3 parameter fields);
- the log and diff readers.

The script goes to `src/flextoolsmcp/scripts/`, as the parent spec (5.3) placed it. It is resolved
at run time with `Path(__file__).parent`, the `file_utils.get_bundled_templates_dir` convention.

---

## Implementation phases

**Reworded (CP5 re-plan 2026-09-24).** These are ordered by dependency and risk, and each phase
names its exit condition. Phase 8 is no longer blocked on M-1 -- every phase can now run to
completion without a maintainer install step, since the sandbox worker loads FieldWorks' own bundled
engine.

### Phase 1 -- Contract and surface first (FR-007, FR-009, FR-034; M-2)

- The detail models, `docs/TOOL-CONTRACT.md` rows, golden fixtures and the CHANGELOG paragraph.
- `ParseSandboxInput`, the ToolDef and the dispatch route, with the handler stubbed to refuse.
- The USAGE.md rows, including `flextools_parse_cancel`.
- The CP5 field-order test block, which parses `contracts/tools.md` section 4.
- **New**: `ParserJobFailedDetail` (`failure: engine_unavailable`, D7).

*Exit*: the contract tests are green at the new count, and `validate_integrity.py server` is clean.

### Phase 2 -- Discovery and health (US1; FR-001, FR-004..FR-007; D7)

**Reworded (CP5 re-plan 2026-09-24).** ~~`parser_probe.py`: the four sources with a recorded
source, the `hc -h` probe (UTF-16 stdout, UTF-8 stderr, closed stdin, 5 s), memoisation~~ is retired.
Instead:
- `parser_probe.py`: resolve the FieldWorks-bundled HermitCrab DLL and `GenerateHCConfig.exe` paths
  via the existing `versioning.get_resolved_fieldworks_dir()`; read each `FileVersion` via `ctypes`.
  No process is spawned and no DLL is loaded (D7).
- The health keys, advisories and `next_step` rows (missing-DLL hint points at repairing/
  reinstalling FieldWorks).
- The CP1 boundary change: add `CP5_SANDBOX_ENGINE_ALLOWLIST` (`Morpher`, `XmlLanguageLoader.Load`)
  scoped to `worker_main.py`'s `--sandbox` mode, and its pin. Remove `HC_IDENTITY_PROBE_ARGS` /
  `HC_PROBE_MODULE` and `TestHcIdentityProbeNarrowing` (QC review P1).

*Exit*: every discovery and health test is green, and S1 is observable here now, on this machine,
without any external install.

### Phase 3 -- The Generate-mode script (FR-014, FR-022..FR-024; contracts/hcparse.md)

**Reworded (CP5 re-plan 2026-09-24).** The script now has one mode, Generate; the fakes and
invariants for Parse/Test move to Phase 5 as sandbox-worker tests.
- The generator fake, written **first**.
- `hcparse.ps1`: Generate mode only -- the allowlist copy, `dispatch.json` and `run.json`, the
  `-ConfigOut` refusal, and `finally`.
- Package data. The root copy deleted.

*Exit*: `test_sandbox_script.py` is green on Windows, covering contracts/hcparse.md's Generate-mode
invariants only.

### Phase 4 -- Paths, workdir, engine, cache (FR-008, FR-011, FR-012, FR-024..FR-026, FR-036/D6, FR-042)

- `paths.py`, `workdir.py` (with the shared `disk_space_ok`), `engine.py` (**updated, D6**: runs
  before any copy and before the sandbox worker is spawned) and `cache.py` (**updated, D3**:
  `key.json` carries `hc_parameters`, excluded from the cache key).
- The invalidation call sites: the filing observer, and `run_module` (guarded and lazy).

*Exit*:
- the cache and workdir tests are green;
- `test_issue55_write_safety_ladder.py` and the `run_module` suites pass **unmodified**;
- the backup tests pass unmodified.

### Phase 5 -- The sandbox worker, classification, the client (US2, US4; FR-013, FR-015..FR-020, FR-027, FR-031..FR-033, FR-035, FR-046..FR-050)

**Reworded (CP5 re-plan 2026-09-24), replaces the original `hc_output.py`-centred phase.**
- `worker_main.py`'s `--sandbox` mode and `_SandboxBackend`: the `AssemblyResolve` handler,
  `XmlLanguageLoader.Load`, `Morpher`, `ParseWord`, per-morph extraction (form/gloss/`guessed`, D5),
  shaping rules a-d against the `--id-map` (D4 reversed, FR-050), parameter application (D3/FR-047),
  D1's message refusals and neutral hooks (`preflight()`, `active_engine()`, `eligible_entries()`,
  `release()` keeps the Morpher).
- `classify.py`, written test-first from the domain review's four-way table. **Reworded (D4 reversed,
  maintainer correction 2026-09-24)**: there are no D4-named gaps left to special-case here --
  shaping (FR-050) happens inside the worker before classification ever sees the analyses.
- `client.py` and the runner branch, spawning one sandbox worker process per run (not pooled, F-13).
  The `parser_timeout` failure path kills that process.
- The `RunMeta` fields, including the new D3/D5 ones.

*Exit*: the client tests drive a real `_execute_run` against the sandbox worker: stream, timeout,
cancel, engine load failure, and two concurrent jobs each with their own worker process. A process-
isolation test proves no LCM/flexicon import (FR-046).

### Phase 6 -- Sandboxes, corpora, the handler (US2-US4; FR-028..FR-030, FR-034, FR-037, FR-040, FR-041, FR-044)

- `store.py`.
- `handle_flextools_parse_sandbox`, following the check order of contracts/tools.md section 3,
  with boom-stubs.
- Responses, advisories, labels, `next_step`.

*Exit*: the handler, store and lifecycle tests are green. Unaffected by the re-plan.

### Phase 7 -- Consumers and corrections (US5; FR-038, FR-039)

- `parse_log` becomes spine-aware; `hc_stdout`/`hc_output` now read from the sandbox worker's
  captured output and structured results (FR-038, reworded).
- The diff `comparison` block, assertion buckets and the either-run staleness rule. The signature
  mode is forced for cross-spine pairs.
- Parent-spec edits: 10.2, 13 and 14.
- The CP5 spec Assumptions fix (R-02, updated for D6).
- CP3 `artifact.md` section 11.

*Exit*: the log and diff tests are green, and in-process log responses are byte-identical.

### Phase 8 -- Live verification (FR-045; quickstart L-1..L-7, S1..S13)

**Updated (CP5 re-plan 2026-09-24): no longer blocked on M-1.** The sandbox worker loads FieldWorks'
own bundled HermitCrab DLL, present on this machine (and any FieldWorks-installed machine), so every
scenario can run without an external install.
- All of S1-S13 and L-1-L-7 can run now, not just S1 and L-5's "before" half.
- ~~Everything else waits for a working `hc`~~: retired. ~~The leading-dash rule, the runtime
  matcher~~ are retired along with FR-013/FR-004's original mechanisms; the BOM and timeout-default
  questions still apply to Generate mode's script.
- The L-answers are folded back into code: the allowlist, the BOM, the timeout default.

*Exit*: evidence files exist, each carrying the two versions (bundled HermitCrab DLL,
`GenerateHCConfig`), and the full suite is green (SC-010). This phase is no longer a `needs_human`
stop by default; it only becomes one if a specific scenario turns up a genuinely new live unknown.

---

## Test strategy

The `lex-qc` plan gate asks for coverage that is *scheduled*, not merely asserted. Every FR has a
row, and each proof names the wrong implementation it catches.

| Requirement | Proof (the wrong implementation fails) | Where |
|---|---|---|
| FR-001 discovery, source recorded | the bundled `SIL.Machine.Morphology.HermitCrab.dll` and `GenerateHCConfig.exe` are located only via `versioning.get_resolved_fieldworks_dir()`; the resolved FieldWorks installation is recorded; an AST scan proves no `HC_TOOL_PATH`, PATH lookup or `dotnet tool list` call remains | `test_sandbox_discovery.py` |
| FR-002 no hard-coded FW folder | an AST/text scan of `hcparse.ps1` finds no `Program Files` or `LOCALAPPDATA` literal; Generate mode's argv always carries `-GenerateHCConfigPath`; the sandbox worker's `--engine-dir` always comes from the resolved path, never a literal | `test_sandbox_script.py`, `test_sandbox_worker.py` |
| FR-003 | **Retired.** There is no `hc` identity to probe; removed with `HC_IDENTITY_PROBE_ARGS` / `HC_PROBE_MODULE` and `TestHcIdentityProbeNarrowing` (D2) | -- |
| FR-004 presence-only health | a missing-DLL fixture gives `found=False, status=unavailable`; a present DLL with an unreadable `FileVersion` still reports `found=True`; no process is spawned and no DLL is loaded by health (an import-guard or a patched loader that would raise if called proves the negative) | `test_sandbox_discovery.py`, `test_parser_health_block.py` |
| FR-005 two versions, no skew | `fieldworks_hermitcrab` and `generate_hc_config` `FileVersion`s are both reported; **no-floor test**: an absurd version still reports `ready`; a text/AST scan proves no `hc_engine_version_skew` advisory code remains reachable | `test_sandbox_discovery.py`, `test_parser_probe.py` |
| FR-006 naming rule | `ready` names the tool with usable `args`; each `unavailable` variant never names it; the swapped nonexistent-tool sweep still catches a fake name | `test_parser_health_block.py` |
| FR-007 refusal before any copy or spawn | a missing bundled DLL or `GenerateHCConfig.exe` gives `parser_tool_missing` (fields in order), `component` naming the DLL by its own name, `install_hint` pointing at repairing/reinstalling FieldWorks; the `work/` root is unchanged and no sandbox worker process is spawned (boom-stub on both `workdir.create` and the worker spawn call) | `test_sandbox_handler.py` |
| FR-008 minimal copy | a fake generator lists its folder: only the allowlist, no `*.lock`, `.hg` or `LinkedFiles`; the copy root is outside the project | `test_sandbox_script.py`, `test_sandbox_workdir.py` |
| FR-009 success judged from output | five fixtures: help-exit-0 (no `Writing completed.`), locked, migration, crash, empty config. Each gives `parser_config_failed` with fields in order and the log captured whole. An exit-code-only judge passes the help fixture and so fails the test | `test_sandbox_cache.py` |
| FR-010 load errors itemised, not refused | a config written with 3 load-error lines gives `load_error_count=3`, the kinds tagged, the run proceeds, the advisory present, and they are carried on a **warm** run too | `test_sandbox_cache.py`, `test_sandbox_handler.py` |
| FR-011 copy always deleted | a parametrised terminal path (success, generator fail, sandbox-worker load fail, timeout, cancel, exception in the client) leaves `work/` empty. Tree-kill-skips-finally: the client's own delete. The startup sweep removes a marked orphan and ignores unmarked dirs | `test_sandbox_workdir.py`, `test_sandbox_client.py` |
| FR-012 2x free space | a patched `disk_usage` below 2x the **allowlist** size gives the refusal with `needed_bytes` and `free_bytes`, and no directory created; the backup tests stay unmodified | `test_sandbox_workdir.py` |
| FR-013 | **Retired.** Words travel as JSON string values over the worker's protocol; there is no quoting, BOM or "not expressible" state to test | -- |
| FR-014 H11 verbatim, retargeted | the `-Words "a,b c"` split is preserved in Python, before the resulting list is handed to the sandbox worker as JSON (not written to a script file); a non-Latin word list round-trips through the worker protocol byte-exactly | `test_sandbox_handler.py` |
| FR-015 ordering | NFC duplicates merged; the count order then alphabetical; `limit` applied after ordering; `truncated_by_limit` recorded | `test_sandbox_handler.py` |
| FR-016 not from exit code | every outcome enum comes from the worker's structured `result.parse` message, never a subprocess exit code; a config that fails to load into a usable `Morpher` gives a failed run reported with the load exception's message and zero word results (`parser_job_failed`, `failure: "engine_unavailable"`) | `test_sandbox_worker.py`, `test_sandbox_client.py` |
| FR-017 totals are the direct sum | a run's summary counts (parsed/not-parsed/error, or pass/regression/new_ambiguity/changed/error) are asserted equal to the sum of the per-word or per-assertion classifications for every terminal run, offline; there is no independent counter left to disagree with | `test_sandbox_worker.py`, `test_sandbox_classify.py` |
| FR-018 exactly one result per word | every outcome enum from fixtures; a crash mid-list gives `error_no_output` plus `not_reached`, **never** `not_parsed`; a count invariant over randomised lists (words sent == results returned) | `test_sandbox_worker.py`, `test_sandbox_client.py` |
| FR-019 direct object read, no column ambiguity | an empty gloss reads as `?`; a form/gloss containing an astral-plane character reads correctly (compared against `word.GetAllomorph(morph)`/`Morpheme.Gloss` directly, never a printed column); there is no `readable: false` state left to produce | `test_sandbox_worker.py` |
| FR-020 / SC-008 timeout | a sandbox worker fixture that sleeps on word 41 of 100 gives `parser_timeout` (fields in order), `words_completed=40`, the in-flight word named, 40 lines in `results.jsonl`, and the worker process tree killed (no separate `hc` process beneath it) | `test_sandbox_client.py` |
| FR-021 ASCII console, Generate mode only | the script's captured stdout is ASCII; `stderr_tail` escapes non-ASCII; an AST/text scan proves no Parse/Test console path remains in `hcparse.ps1` | `test_sandbox_script.py` |
| FR-022 packaged, invoked safely, Generate mode only | the wheel contains `scripts/hcparse.ps1`; the argv is a list starting with the exact invocation; no `-Command` or `Invoke-Expression` anywhere; the script has exactly one mode (`Generate`) | `test_sandbox_script.py` |
| FR-023 `run.json` folded, Generate mode only | the meta is built from `run.json` and flushed files only, for Generate mode; an AST check that the client never reads the script's stdout for data; Parse/Test results are asserted to arrive only over the worker's JSON-lines protocol, never folded from a script hand-off file | `test_sandbox_script.py`, `test_sandbox_client.py` |
| FR-024 version constant keys the cache | exactly one `HCPARSE_VERSION` match; bumping it changes the key | `test_sandbox_cache.py` |
| FR-025 / SC-007 three lifecycles | prune, invalidate and rebuild leave sandbox and corpus bytes identical; an AST check that every deleter guards its root; an in-use entry survives prune; `hc_parameters` (and `lcm-ids.json`'s path) are excluded from the cache key | `test_sandbox_lifecycles.py`, `test_sandbox_cache.py` |
| FR-026 invalidation, `-ConfigOut` confinement | a CP4 `after_terminal` and a successful write-enabled `run_module` each invalidate; a read-only `run_module` does not; an AST check that `-ConfigOut` is passed only by `cache.build_entry`; the script exits 3 under `sandboxes` | `test_sandbox_cache.py`, `test_sandbox_script.py` |
| FR-027 corpus schema validation | a non-string form/gloss, a missing key, or a zero-morph expected-parse entry gives an invalid-entry result; the rest of the corpus still runs; no delimiter character is ever treated as unexpressible | `test_sandbox_classify.py` |
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
| FR-045 live (**reworded, CP5 re-plan 2026-09-24**) | quickstart S1-S13, L-1-L-7, run against the sandbox worker's `--sandbox` mode and the real FieldWorks-bundled DLL -- no external `hc` install is a precondition. Evidence records the two versions (bundled DLL, `GenerateHCConfig`), not three | `test_parse_live_cp5.py` (**no longer M-1-blocked**) |
| SC-001 no copy remains; project byte-identical | FR-011's parametrised terminal paths, plus FR-043's before-and-after hash, asserted together in one test per path; **new**: FR-046's process-isolation check (no LCM/flexicon import) holds throughout | `test_sandbox_workdir.py`, `test_sandbox_no_project_writes.py`, every live scenario |
| SC-002 health names the right cause (**reworded, D7**) | FR-004's missing-bundled-DLL fixture and FR-006's never-named sweep. ~~cannot-start fixture~~ retired: a DLL that fails to load is proven instead by a `test_sandbox_worker.py` fixture forcing `parser_job_failed` (`failure: engine_unavailable`) on the first run, not by a health test | `test_parser_health_block.py`, `test_sandbox_worker.py`, live S1 |
| SC-003 parity with Try A Word (**reworded, CP5 re-plan 2026-09-24; D4 reversed by maintainer correction -- domain review's (a)-(d) definition**) | **Live** (L-6), covering (a) matching parsed/not-parsed/invalid-segment outcomes and `(form, gloss)` sequences, now including circumfixed and previously-unresolvable-id words, since FR-050's shaping rules and the validated `lcm-ids.json` id map replicate `HCParser.GetMorphs` rather than skip it; (b) guessed-root analyses (FR-048) compared as their own category via `Guessed`, never lumped in; (c) the applied `ParserParameters` (FR-047/D3) match the project's, or FLEx's defaults when absent; (d) the two remaining named differences (glosses from the exported `Morpheme.Gloss` rather than live senses, and a named sandbox's user-added morphs, `user_added: true`) are asserted as *named, disclosed* differences in the comparison output, not silently passed or silently failed; a fixture with an unresolved id in `lcm-ids.json` is asserted to fail the run as `parser_job_failed` (`failure: "id_map_invalid"`), never to shape silently wrong. Version-matching is now automatic (the sandbox always loads FieldWorks' own DLL), so there is no "version-skewed, partially verified" outcome any more -- either it is fully verified or a genuine mismatch is a bug | `test_parse_live_cp5.py`, `test_sandbox_worker.py` (D3/D4/D5/FR-050 fixtures offline where source-derivable) |
| SC-004 zero silent losses | FR-018's randomised count invariant (words sent == results) | `test_sandbox_worker.py`, `test_sandbox_client.py` |
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

**Live verification.** It is mandatory, read-path, with a byte-identity hash on every scenario.
**Updated (CP5 re-plan 2026-09-24): no longer blocked on M-1** (quickstart) -- M-1 is resolved.

---

## Complexity Tracking

| Violation / complexity | Why needed | Simpler alternative rejected because |
|---|---|---|
| A new `server/sandbox/` package (server-side policy: Generate mode, paths, cache, classification, store) | Generate mode's risks (disk, subprocess) and the three lifecycles need their own boundary and tests. `parse/` carries the in-process spine's standing no-write proofs | Folding it into `parse/` mixes subprocess and file-deletion code into modules whose structural tests assume neither |
| ~~CP1 invariant narrowed (R-04): discovery may run `hc -h`~~ **Superseded (D2, CP5 re-plan 2026-09-24)** -- **CP1 invariant grows a scoped exception**: `Morpher` / `XmlLanguageLoader.Load` are permitted inside `worker_main.py`'s `--sandbox` mode via `CP5_SANDBOX_ENGINE_ALLOWLIST` | The sandbox worker must call the real engine in-process; the CP1 boundary's point (health/discovery load no grammar) is preserved by scoping the exception to a mode that never runs during health or discovery | A file-only probe cannot observe an engine load at all; the alternative of keeping the parser call out of `worker_main.py` entirely would violate the design of record (mechanism reuse) and duplicate the `ParseWorker` loop elsewhere |
| The Generate-mode script is invoked once per cold job; the sandbox worker is a separate process launched by the client (**reworded, CP5 re-plan**: no longer "the script is invoked twice") | The cache lock must cover generation only (R-01); Parse/Test no longer share the script's process at all | One invocation holding the lock for the whole parse would make a second job wait hours; splitting Generate from Parse/Test also removes any question of the lock spanning both |
| ~~`run.json` per-word entries record dispatch, not interpretation (R-01)~~ **Moot (CP5 re-plan 2026-09-24).** There is no `run.json` per-word entry for Parse/Test at all any more; the sandbox worker's JSON-lines messages **are** the interpretation, produced directly from the .NET objects, with no separate "dispatch vs. interpretation" split to flag | n/a | n/a |
| A per-run client outside `WorkerPool` | The pool keys by `(project, role)` (F-13), and concurrent sandbox jobs need separate engine instances | Keying the pool by run id changes pooling for every role |
| `parse_sandbox_refused` (M-2) | Six refusal kinds have no code among the 34 (R-16) | `runtime_error` violates Principle V; six codes bloat the surface for one tool |
| **New (CP5 re-plan 2026-09-24)**: `parser_job_failed` (D7) as a distinct code from `parser_tool_missing` | A present-but-unloadable DLL is a different failure mode from an absent one, and Principle V wants a teachable code for each, not a shared vague one | Reusing `parser_tool_missing` for a load failure would say "not found" about a file that is, in fact, found -- actively misleading |
| **New (CP5 re-plan 2026-09-24)**: parameter-source priority chain (cache / live_project / flex_defaults, D3) | The Morpher's five settings can come from three different places depending on config source, and SC-003 needs the right one used and recorded | A single fixed source (e.g. "always FLEx defaults") would silently break parity for any project with non-default `ParserParameters`, which the domain review found is common enough to matter |
| **New (D4 reversed, maintainer correction 2026-09-24)**: a validated `lcm-ids.json` sidecar, generated server-side and consumed by the worker via `--id-map` (FR-050) | Try A Word's shaping rules (a-d) need each id's LCM class, which the exported grammar itself does not carry; the mapping's HVO-equals-`rt`-order reading is an observed behaviour, not a documented contract, so it must be validated rather than trusted | Reading ids from the config alone (no sidecar) cannot tell a `MoForm` id from an MSA id from an `InflTypeID`, so rule (d) could never be applied safely; trusting the HVO-order reading unvalidated would risk shaping silently wrong on a future FieldWorks/LCM version |

---

## Risks

| Risk | Handling |
|---|---|
| ~~No working `hc` for live verification~~ (R-15) | **Resolved (CP5 re-plan 2026-09-24, M-1 closed).** The sandbox no longer needs `hc`: it loads FieldWorks' own bundled HermitCrab DLL in-process. Phase 8 runs on any FieldWorks-installed machine, including this one, with no `needs_human` stop for this reason. See research.md R-17 for the option comparison |
| **New (CP5 re-plan 2026-09-24)**: the sandbox worker fails to load the bundled DLL at run time, though health reported it present (D7) | Surfaced as `parser_job_failed` (`failure: engine_unavailable`), never as a health-time finding. This is deliberately narrower than the retired "cannot start" health state -- see spec.md FR-004 |
| **New (CP5 re-plan 2026-09-24)**: `SIL.Core` version mismatch between the HermitCrab DLL's expected dependency (17) and FieldWorks' shipped one (18) | An `AssemblyResolve` handler loads any assembly by simple name from the FieldWorks folder, proven live in `reference/hc_fw_prototype.py`'s `Engine.__init__` (HANDOFF.md) |
| **New (CP5 re-plan 2026-09-24)**: `MaxAlternatives` is absent from the Morpher in HermitCrab 3.8.2 (present from 3.9.1) | Applied only when the loaded `Morpher` exposes the property; recorded in `parameters_applied` so its absence is visible, never silently skipped (D3/FR-047) |
| The allowlist copy is not enough for `GenerateHCConfig` (L-1) | It fails loudly as `parser_config_failed`, never as a grammar problem. L-1 extends the allowlist, and the free-space measure follows it. Unaffected by the re-plan (Generate mode) |
| ~~The UTF-16 decoding is wrong in PowerShell 5.1~~ (L-3) | **Moot for Parse/Test (CP5 re-plan 2026-09-24).** There is no `hc` console output to decode; the sandbox worker returns structured .NET objects directly. Still relevant to Generate mode's own console capture, unaffected there |
| A stream read of a large `.fwdata` is slow | Early exit at the first `MoMorphData`. The result is cached in `key.json` by `(path, size, mtime)`. Measured in S4. Unaffected, except it now also gates spawning the sandbox worker (D6) |
| Reading `.fwdata` while FLEx saves it gives a spurious XAmple refusal | One retry. The hint names "could not be read" as distinct from "is XAmple". L-7 |
| Cache invalidation raises inside `run_module` | A lazy, guarded import and try/except, logged and never propagated. The ladder suite passes unmodified |
| Windows sharing violations on deletion | Retries, and a recorded `cleanup: failed` with the path, swept next time. Never silent |
| ~~hc and FLEx disagree at matching versions~~ (L-6) | **Moot (CP5 re-plan 2026-09-24).** There is only one engine now -- FieldWorks' own -- so there is nothing to disagree with by version. The residual differences are SC-003(d)'s two named ones (glosses from the exported `Morpheme.Gloss`, and user-added morphs in a named sandbox), never hidden; `results_label` already says these are the sandbox's results |
| **New (D4 reversed, maintainer correction 2026-09-24)**: the id map's HVO-equals-`rt`-document-order assumption (`lcm-ids.json`) is an LCM XML-backend load-order behaviour, not a documented contract, and could break on a future FieldWorks/LCM version | Guarded by validation: any id that does not resolve to the expected class marks the map invalid and fails the run as `parser_job_failed` (`failure: "id_map_invalid"`) rather than shaping silently wrong. Also checked live against a circumfix project (e.g. `Circumsanity` under `C:\ProgramData\SIL\FieldWorks\Projects`), via a scratch copy only |

---

## Open maintainer decisions

| # | Decision | Default taken so planning is not blocked | When it must be settled |
|---|---|---|---|
| **M-1** | ~~How to get a working `hc` for FR-045...~~ **Resolved (2026-09-24, HANDOFF.md).** The maintainer chose option 2 of 3: drop the `hc` CLI; parse in the worker against FieldWorks' bundled engine. See research.md R-17 | Resolved; no default needed | Closed |
| **M-2** | Add `parse_sandbox_refused` (a seventh code beyond the spec's list) for name, existence, corpus, seeding and disk refusals | Add it (count 34 to 36) | Before Phase 1 lands. Overturning it later changes the contract rows |
| **M-3** | ~~FR-023 reading: `run.json` per-word entries record dispatch; Python interprets hc's output (R-01)~~ **Moot (CP5 re-plan 2026-09-24).** There is no script hand-off for Parse/Test to argue about; the worker's structured messages are the interpretation directly | n/a | Closed |
| **M-4** | Q2 is still open in the spec (seeding source). ~~Q3 (skew policy)~~ is moot -- there is no engine to be skewed against (D7) | The spec's default for Q2: baseline seeding | Before `/speckit.tasks`, or accepted as written |
| ~~**New: M-5**~~ | ~~Whether to also implement D4's circumfix-doubling / `FormID==0`-skipping replication from the exported `Properties` in CP5, or defer it as a named SC-003(d) gap~~ **Resolved (maintainer correction, 2026-09-24): D4 reversed.** These are FLEx's own Try A Word display rules, not bugs; CP5 replicates them via a validated `lcm-ids.json` id map (spec.md FR-050, research.md D4) | Build it; not deferred | Closed |
