# parser-check CP5 (sandbox spine): as built

**Status:** Retired 2026-09-29. Two squash merges to main: `06f90a8` (PR #231, 2026-09-24, the original `hc`-CLI design) and `941d805` (PR #266, release 2.13.0, 2026-09-25, the re-plan that moved Parse/Test into the parse worker). Tasks: 115/115 checked (T001-T115; T095 superseded by Phase 10).
**Full docs:** [specs/_archive/parser-check-cp5/](../_archive/parser-check-cp5/) (spec, plan, tasks, research, data-model, contracts, HANDOFF, reviews, reference, evidence). Not read by default.
**Pinned (archive):** `tests/test_parser_error_models.py` reads `contracts/tools.md`; `tests/test_parse_live_cp5.py` writes live evidence to `evidence/`, both under `specs/_archive/parser-check-cp5/`.
**Scope:** Issue #166. The third parser-check spine: a rehearsal space that never touches the live project. Successor CP6 (#167, PR #291) added `next_step` rungs and telemetry on top.

## What shipped
- `flextools_parse_sandbox` (read-only), actions `parse`, `create_sandbox`, `seed_corpus`, `run_corpus`, `list` (`models.py:1125`).
- Generate: `src/flextoolsmcp/scripts/hcparse.ps1` (`HCPARSE_VERSION` 6.0.0, Generate mode only) makes an allowlisted project copy, runs `GenerateHCConfig.exe`, always deletes the copy.
- Parse/Test: the parse worker's `--sandbox` mode (`worker_main.py`, `_SandboxBackend`, flags `--sandbox/--config/--hc-params/--id-map/--engine-dir`) calls FieldWorks' own `SIL.Machine.Morphology.HermitCrab.dll`: `XmlLanguageLoader.Load` -> `Morpher` -> `ParseWord`. No flexicon, no LCM, no project open.
- `server/parse/hc_engine.py`: pure helpers (engine dir, HC parameters, id map, `shape_analysis` port of `HCParser.GetMorphs`).
- `server/sandbox/`: `paths`, `engine` (stream read of ActiveParser), `workdir`, `cache`, `lcm_ids`, `script`, `classify`, `store`, `client`.
- Cache invalidated after CP4 filing and write-enabled `run_module` runs (`execution.py:2870`), guarded, never propagates.
- Health `parser.sandbox` components `fieldworks_hermitcrab` + `GenerateHCConfig.exe` (`diagnostic_health.py:~300`).

## Public contracts
- New codes `parser_config_failed`, `parse_sandbox_refused` (closed `reason` enum); first emitters of `parser_tool_missing` (`component`: `"fieldworks_hermitcrab"` | `"GenerateHCConfig.exe"`) and `parser_timeout`. `parser_job_failed.failure` gains `engine_unavailable`, `id_map_invalid`. See `docs/TOOL-CONTRACT.md:142-154`. Envelope stays `tool-responses/1.0`.
- Worker protocol: `contracts/sandbox-worker.md`; script: `contracts/hcparse.md` (cited by `hcparse.ps1`, `hc_engine.py`, `worker_main.py`, `sandbox/*.py`, `response_models.py:837`).
- Disk: `~/.flextoolsmcp/parse/` (override `FLEXTOOLSMCP_PARSE_SANDBOX_DIR`), checked outside every project folder (FR-042). `sandboxes/` and corpora are user-owned, never deleted; cache prune keeps 3 (`cache.DEFAULT_KEEP`).
- Each morph: `form`, `gloss` (`Morpheme.Gloss`, `?` if empty), `guessed` (`allomorph.Guessed`), `is_circumfix`, `user_added`.

## Key decisions
- Re-plan (HANDOFF, R-17): FieldWorks 9 ships the engine but not `hc`; parse in the existing worker rather than ship an `hc` stand-in (rejected, kept in `reference/`) or drop sandbox parsing.
- D1: `--sandbox` refuses project-bound messages (FR-049); keeps the Morpher loaded per run instead of per-word release.
- D2: `CP5_SANDBOX_ENGINE_ALLOWLIST = {worker_main.py: "_SandboxBackend"}` (`tests/test_cp1_boundary.py:972`); `hc -h` probe removed.
- D3/FR-047: `ParserParameters/HC` applied (`DeletionReapplications`, `MaxStemCount`, `MergeEquivalentAnalyses`, `MaxAlternatives` if present, `guessRoot`); source `key.json` > live `.fwdata` stream read > FLEx defaults `0/2/true/true/0`.
- D4/FR-050: replicate Try A Word shaping (FormID-0 skip, circumfix both sides, dedupe, drop unresolved), using an `lcm-ids.json` sidecar written at Generate time; invalid map fails the run, never skips shaping.
- D6: engine check runs before the copy and before any worker spawn. D7: health checks DLL presence + `FileVersion` only; load failures surface at first run; skew advisory removed.
- Generation judged from output (`Writing completed.`), not exit code. `new_ambiguity` never counts as unchanged or fixed.

## Gotchas and limits
- `lcm-ids.json` relies on HVO == 1-based `<rt>` document order in `.fwdata`: an LCM load-order behaviour, not a contract. Verified live on two projects (S14) only.
- Engine targets `SIL.Core` 17 vs FieldWorks' 18; the `AssemblyResolve` handler (`worker_main.py:2171`) is required.
- Test projects are IPA (`IndonesianHC-Complete`); Latin words hit `invalid_segment`. Live tests must run on scratch copies only.

## Divergences from the spec
- SC-006 (warm run at least 2x faster) not met live: S5 ratio 1.82, recorded `needs_human: true`. Tasks show T110 checked anyway.
- Clarification Q1's `dotnet tool install -g ...` install hint is obsolete; shipped hint is `parser_probe.FIELDWORKS_REPAIR_HINT`, which names only `GenerateHCConfig.exe` even when the missing component is the HermitCrab DLL (`handlers/parse.py:2842-2843`).
- `hcparse.ps1` Parse/Test were not deleted outright: the script now refuses them with a "retired" message (`hcparse.ps1:234`).
- Evidence `s1-health-no-hc.json` predates the re-plan (describes `hc` discovery); `s-issue69-langproject-live-verify.json` belongs to #69, not CP5. No S2/S7 evidence files; no dedicated apostrophe-word file (S4 includes `ma'af`).
- The spec header still says "Status: Draft".
- Not verified: FR-001..FR-050 individually, SC-001..SC-010 beyond the evidence summaries above.

## Follow-ups and open issues
- #235: #223 per-word project reopen (D8, out of scope).
- SC-006 live timing decision (accept 1.8x or open an issue).
