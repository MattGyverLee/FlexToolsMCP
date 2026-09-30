# parser-check CP2a-bridge + CP2b: as built

**Status:** Retired 2026-09-29. Landed directly on main (first-parent history, no PR): `9cb8af6` "CP2b complete" (2026-09-20), follow-ups `078d8e8` + `33ce8a3`, merged with main in `e5afbfd`; outcome-reporting follow-up `84a2f9d` landed on main after it. Tasks: 68/68 complete. Flexicon side (R-08 tests) is flexicon PR #354 (`85e0eab`).
**Full docs:** [specs/_archive/parser-check-cp2b/](../_archive/parser-check-cp2b/) (spec, plan, tasks, research, data-model, contracts/tools.md + bridge.md, quickstart, reviews, [evidence](../_archive/parser-check-cp2b/evidence/cp2b-evidence.md)). Not read by default.
**Pinned (archive):** `tests/test_parse_live.py` writes `evidence/sc004-inline-rate.json` into `specs/_archive/parser-check-cp2b/evidence/`.
**Scope:** This spec is a *scoping* doc; the authoritative requirement text is parser-check-cp2's spec (FR-011..FR-040, US2-US4). CP2a (the flexicon facade) is [../parser-check-cp2/AS-BUILT.md](../parser-check-cp2/AS-BUILT.md).

## What shipped
- **Bridge (FR-011):** pyflexicon floor raised and bundled indexes regenerated to match; `tests/test_flexicon_index_floor.py` asserts floor == `versioning.py`-resolved version == every flexicon index artifact (deliberately not `importlib.metadata`).
- **`flextools_try_word`** (`READ_ONLY_SAFE`): one word, three levels -- `plain` (yes/no), `explain` (full trace), `restricted` (caller's decomposition in `morphs`).
- **`flextools_parse_status`**: poll a run by `run_id`.
- **Morph resolver** (`server/parse/resolver.py`): headword / headword+sense / id input, lookup index built once per run, refusal on any unresolvable piece, bounded proposal assist.
- **Run machinery** (`server/parse/`): long-lived per-project parse worker (`worker_main.py`, `worker_client.py`) over line-delimited JSON; `runner.py`, `stages.py`, `priority.py`, `queue.py`, `record.py`.
- Three additive refusal codes in `docs/TOOL-CONTRACT.md`: `parse_morph_unresolved`, `parse_run_not_found`, `parse_job_cancelled`.
- Flexicon: offline tests for the three CP2a read gaps (`tests/operations/test_text_genres.py`, `test_allomorph_owner.py`, `test_msa_read.py`).

## Public contracts (checked against code at `0715b64`)
- Tool defs: `server/tool_definitions.py:485` (try_word, `annotations=READ_ONLY_SAFE`), `:533` (parse_status). Handlers: `server/handlers/parse.py`.
- Stages (`stages.py:60`): `starting, loading_grammar, parsing, filing, completed, failed, cancelled`. `filing` had no inbound edge in CP2b (CP4 later gave it a producer for one run kind). Warm path `starting -> parsing` exists for a held grammar.
- Priority (`priority.py:44`): `RELOAD_GRAMMAR_AND_LEXICON=0, TRY_A_WORD=1, HIGH, MEDIUM, LOW`; a single word overtakes a batch at a word boundary.
- Grace window: `runner.py:110` `DEFAULT_GRACE_WINDOW_SECONDS = 5.0`, env `FLEXTOOLSMCP_PARSE_GRACE_WINDOW`. Past it the caller gets a bare `run_id`; the window closing never cancels or slows the run.
- Run record: `results.jsonl` appended and flushed per word (`record.py:116`), so a killed worker loses 0 results.
- `parse_morph_unresolved` detail: exactly `morph, position, resolved_to (none|ambiguous|no_msa), candidates, hint`; `msa_hvo: null` is the `no_msa` signal. No parse runs.
- `parse_run_not_found` is the only refusal `parse_status` issues; asking about a terminal run is a success, not `parse_job_cancelled`.
- Level outcome fields (`84a2f9d`): `explain` -> `parsed`, `analysis_count`; `restricted` -> `hypothesis_held`, `restricted_analysis_count` (never `parsed`); either may instead carry `parse_error` (trace had `<Error>` or no `Root`) and then emits neither. Derived from the trace's `<Analysis>` children (`worker_main.py:1675` `_summarize_trace`), no second parser call. `result_summary` (`parse.py:4333`) counts `parsed` only over plain results plus a separate `hypotheses_held`.
- `SC-003` standing test `tests/test_parser_no_xcore.py` (`HCParser_DoesNotLoadXCore`) asserts against the **worker's** assembly *delta* around a real Update + ParseWord.

## Key decisions
- The server never opens a project (R-02); the held grammar lives in a worker process (D-B2).
- Engine gate runs as the worker's first action, not the handler's first statement (D-B3). FR-015 guarantees order, not latency: a cold refusal may arrive after the grace window as a run handle.
- Empty restriction is refused before the facade (`parse_morph_unresolved`), never passed as an empty iterable (Delta 2).
- A `CAPABILITIES` token is not a reachability probe; call `GetAvailability()` (Delta 4).
- Restricted and unrestricted answers use different field names so they cannot be compared as the same question (Delta 6).
- Delta 7 (per-analysis signature inline) was spec'd, not built; CP3's durable signature shape is the one to reuse.
- Grammar lints deferred to CP3 (D5, FR-040); CP1's boundary regression amended, not deleted (D-B6).

## Gotchas and limits
- Worker stream limit raised to 64 MiB (`subprocess_helpers.py:26`) because inline `trace_xml` blew asyncio's 64 KiB `readline()` and killed the channel. A ceiling, not a fix.
- The live tier writes to real projects (see memory note); run suites with `-m "not requires_flex"` unless you mean it.
- Issue #223 later scoped "held grammar" to while the project is open: the worker closes the project when idle and reopens on demand.
- T009 (published distribution installs in a clean env) was **NOT RUN**.
- Measured: SC-004 inline rate 24/24 (median 47 ms); full suite 2046 passed / 0 failed at `078d8e8`, 2120 passed at `84a2f9d`.

## Divergences from the spec
- FR-041/SC-016 "0 lines changed in `parser_probe.py`": 37 comment lines were added (the requirement contradicted itself); "unchanged" is now proven by AST equality in `tests/test_parser_probe.py`.
- SPEC 16 / CP2-SPEC phrase `HCParser_DoesNotLoadXCore` absolutely; unsatisfiable (opening a project loads WinForms), so the test asserts the parse-path delta. Parent specs were not restated.
- Floor: spec asked for `>=4.9.0,<5`; repo now requires `>=4.11.0,<5` (later bridges).
- Branch: spec proposed `feat/parser-check-cp2`; work stayed on `feat/parser-check-cp1` (T001).
- `078d8e8` deleted the dead casting-injection functions; `33ce8a3` restored them (out of scope for an additive campaign); PR #217 (`2772b52`, fixes #163) later retired them properly. The false `Preflight: passed (tier=full)` telemetry fix stayed.
- Data-model stage diagram lacked the warm `starting -> parsing` edge; added (T033).

## Follow-ups and open issues
- SPEC 16's no-oracle case remains deferred (no review surface in CP2b).
- `worked_examples.py:237` teaches a keyword-bound collection parameter (doc nit, T042).
- Flexicon `HeadlessLcmUI` null `SynchronizeInvoke` finding from T066 (recommended upstream filing).
- Recommended: restate SPEC 16 / CP2-SPEC `HCParser_DoesNotLoadXCore` in delta terms.
