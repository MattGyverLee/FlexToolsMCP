# parser-check (umbrella, CP1-CP6): standing contracts

**Status:** Retired 2026-09-29. This was the umbrella spec for all six checkpoints and the home of CP1's plan and tasks. CP1 landed directly on main in merge `e5afbfd` (2026-09-20, "Merge origin/main into parser-check CP1+CP2+CP2b"); no PR exists. CP1 tasks: 35/35 complete (`aed4837`, `70a189a`, `988151d`; WS fix `b896633`). The later checkpoints shipped from their own folders: CP2/CP2b, CP3, CP4 (PR #216), CP5 (PR #231), CP6 (PR #291).
**Full docs:** [specs/_archive/parser-check/](../_archive/parser-check/): [SPEC.md](../_archive/parser-check/SPEC.md) (umbrella requirements, amended through CP5), [plan.md](../_archive/parser-check/plan.md), [tasks.md](../_archive/parser-check/tasks.md), [research.md](../_archive/parser-check/research.md) (D1-D11), [data-model.md](../_archive/parser-check/data-model.md), [contracts/](../_archive/parser-check/contracts/), [reviews/](../_archive/parser-check/reviews/). [CP2-SPEC.md](../_archive/parser-check/CP2-SPEC.md) and [CP3-SPEC.md](../_archive/parser-check/CP3-SPEC.md) are drafts that the `parser-check-cp2`/`-cp3` folders replaced. You don't need to read these by default.
**Pinned (archive):** `tests/test_grammar_health.py` reads [`contracts/flextools_grammar_health.md`](../_archive/parser-check/contracts/flextools_grammar_health.md) at runtime (the JSON Output example and the literal phrases "Never derived from wordforms or analyses", "IWfiAnalysis", "Constructs no `HCParser`", "Opens no `LcmCache`").

## Standing rules (from SPEC; every checkpoint still honors them)
- **Never infer parseability from database state** (SPEC 3.1). Having analyses or wordforms does not mean the project parses.
- **Never report the wrong engine's results** (SPEC 3.2). `check_active_parser(project, supported_engines=("HC",))` is the first thing every spine runs. It re-reads `ActiveParser` on every call, and a corrupt `ParserParameters` value reads as XAmple and is refused. The only live caller is `parse/worker_main.py:1030`.
- **There is no version floor.** Versions are reported (`detected.*`, `detected_version`) and never compared.
- **Health is per spine.** `read`, `write` and `sandbox` are each `ready` or `unavailable`, with no `degraded` state. One dead spine doesn't blank the others.
- **Responses summarise and never inline the full result set** (S7). Parse work is split between flexicon (read facade) and the MCP (filing plus the confirmation ladder), and flexicon ships first (S9).
- **Safety** (SPEC 12): each mode is judged on its own; filing can delete analyses (P0-1); the grammar can shrink without warning (P0-2); the HC agent may be missing (P0-3). CP4 built the write ladder from these sections.
- **Error codes:** all of SPEC 14's codes are live in `docs/TOOL-CONTRACT.md`, which is now the source of truth, not SPEC 14. The additions stayed within `tool-responses/1.0`.

## CP1 as built (checked against this repo at `0715b64`)
- `src/flextoolsmcp/server/parser_probe.py`: the ParserCore capability probe (in-process `Assembly.LoadFile` reflection only). `HCPARSER_MEMBERS` covers the read spine. `WRITE_REQUIRED_MEMBERS` is the same set plus `ParseFiler.ProcessParse`, so "read ready / write unavailable" can be represented. It also has `probe_hc_agent`, `ParserDetector`, and sandbox component discovery (`discover_fieldworks_hermitcrab`, `discover_generate_hc_config`).
- `flextools_health` `parser` block: `handlers/diagnostic_health.py:_build_parser_block`. `agent_probe` is always `"skipped"` and `active_engine` is always `None` there, because health never opens a project (research D2, D8). `next_step` rungs are added for unhealthy spines.
- `flextools_grammar_health`: `handlers/grammar_health.py` plus `scan/grammar_scan_module.py:run_grammar_scan`. The scan runs in the generated-module subprocess through `execution.run_scan_module` (D1, D11) and never in the server process. Its input is `GrammarHealthInput` (`project_name`, `checks`, `limit=20`). It returns `next_step: null`.
- The four CP1 error codes have detail models in `response_models.py` (`extra="forbid"`): `parser_engine_mismatch`, `parser_core_missing`, `parser_agent_missing`, `parser_tool_missing`.
- Tests: `test_parser_probe`, `test_parser_health_block`, `test_grammar_health`, `test_grammar_scan_checks`, `test_parser_agent_probe`, `test_parser_engine_gate`, `test_parser_error_models`, `test_cp1_boundary`, and fixtures in `tests/fixtures/parser_check.py`.

## Key decisions (research.md)
- D1/D11: the MCP server process never opens a project. The scan imports `flextoolsmcp.server.scan.*` in the subprocess and returns its results through `report.Result`.
- D3: the capability probe runs in-process and uses reflection only. `HCParser` is never instantiated by CP1 code.
- D7: grammar-health output has no scalar score, total or magnitude ordering, and no verdict words. A finding names a *suspect*. Findings stay in SPEC 9.5.4 row order, and tests enforce all of this.
- D10: HermitCrab's `GrammarHealthChecker` is not in the installed assembly, so the PanGloss lints were not available for free.

## Gotchas and limits
- `test_cp1_boundary.py` was narrowed at CP2b (research R-06). It now guards the CP1 diagnostic surface rather than the whole repo. The one exception is `parse_operation`, which is allowlisted only in the parse worker. Parser construction is still forbidden everywhere.
- Every multistring must be resolved at a named writing system (default vernacular for forms, default analysis for names) before it is tested for emptiness or serialized. Comparing a raw `IMultiUnicode` to `""` is always False. That bug made rows 1 and 6 always report zero until `b896633`.
- Nothing parser-related runs in CI, because the `[windows, fieldworks]` runner pool is empty.

## Divergences from the spec
- **Grammar-health checks:** 12 check slots ship (rows 1, 2, 3a, 3b, 4, 5, 6, 7a, 7b, 8, 9, 10). The contract expected rows 3b, 5 and 7 to be in `checks_skipped`, but D9 confirmed their LCM names, so `checks_skipped` is always empty. `skipped_check()` is kept as a fallback, and the contract's JSON example still shows a skipped entry.
- **Row 1 slot conditioning:** the contract said the slot-reachability walk would come back at CP2. It never did. Row 1 still counts every zero-surface `IMoForm` across the whole project.
- **PanGloss lints:** D10 deferred all three lints to CP2. Rows 6 and 9 now carry `hc-partial-morpheme` and `hc-duplicate-feature-bundle` as their own LCM checks. `hc-undeclared-segment` exists nowhere in `src` or `tests`.
- **`hc` tool retired (CP5 re-plan, issue #167):** `parser_tool_missing.component` is `fieldworks_hermitcrab | GenerateHCConfig.exe`. Detection is filesystem-only and never uses `dotnet tool list -g`. The health-block contract was updated in CP6 (`0c4e488`). `contracts/error-codes.md` and SPEC 14/15 still say `"hc"`.
- **SPEC 14 is stale relative to `TOOL-CONTRACT.md`:** `parser_job_failed.failure` gained `engine_unavailable | id_map_invalid`; `parse_job_cancelled` and `parse_sandbox_refused` were added; `next_step` rungs were added to timeout, job-failed and config-failed (CP6); `parse_run_not_found` gained `hint`. The contract now has 44 codes (CP1 took it from 18 to 22).
- **Module path:** the plan names `server/diagnostic_health.py`, but the file is `server/handlers/diagnostic_health.py`.
- **Not verified:** the SPEC 16 test groups individually, and the flexicon-side facade (see `parser-check-cp2`'s one-pager).

## Follow-ups
- SPEC 17 open questions were not re-audited at retirement. 17.10 (a lazily created HC agent) was assigned to CP4's live verification.
- Citations to `specs/parser-check/...` in `STATUS.md` are historical and were left as written.
