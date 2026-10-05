# Implementation Plan: Run on the mcp 2.x line only, and validate tool input before the session gate

**Branch**: `spec/mcp-modernization` | **Date**: 2026-10-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/mcp2-only/spec.md`. The umbrella
roadmap's engineering detail is `specs/mcp-modernization/contracts.md`
sections 3 (PR-B1) and 4 (PR-B2). This plan cites it and does not repeat it.

## Summary

Move the server to `mcp>=2.3.0,<3` and delete the 1.x/2.x shim. Registration
goes through one thin adapter on the SDK's low-level `Server`. The adapter
keeps the three shim behaviors the SDK does not provide: schema pre-validation,
catching escaped exceptions, and result wrapping (research R2, R3). The wire
output stays byte-identical to the PR-0 goldens in both protocol eras (CP1,
release 3.0.0).

After CP1 merges, CP2 moves tool lookup and input-model validation ahead of
the cold-session gate, sets the error flag on four hard error codes, and bumps
the contract to `tool-responses/1.1` (release 3.1.0).

## Technical Context

**Language/Version**: Python >=3.10 (CI: 3.10 and 3.12; 3.14 floor marker for anyio)

**Primary Dependencies**: `mcp>=2.3.0,<3`, `pydantic>=2.12`, `anyio>=4.9`,
`jsonschema>=4.20` (new explicit), `httpx>=0.27.1` (kept),
`sentence-transformers>=2.3.0` (floor ratchet, research R6)

**Storage**: N/A (no index or schema change; the release-order rule does not apply)

**Testing**: pytest under `.venv\Scripts\python -m pytest`, the in-process
`mcp.client.Client` in both modes, a stdio subprocess client, and the PR-0 wire
goldens

**Target Platform**: Windows (primary, required CI), Linux (no-FieldWorks smoke)

**Project Type**: local stdio MCP server (Python package `flextools-mcp`)

**Performance Goals**: no regression; the stdio handshake completes within the
60 s test timeout on CI runners

**Constraints**: no wire change in CP1; the live maintainer server must not
break (work stays off its editable install until the merge plus the
reinstall sequence); plain ASCII console output

**Scale/Scope**: about 31 tools; 13 files reference the shim today (2 src, 1
`server/__init__`, 7 tests, packaging x2, CHANGELOG)

## Constitution Check

*Source: `.specify/memory/constitution.md` v1.1.0.*

- [x] **I. Safety-First Write Path**: no change to what any tool writes, but
      CP2 reorders the dispatcher in front of the cold-session gate that arms
      `write_enabled` for `run_module`. So CP2 carries a write-safety test (the
      gate reads validated values; see CP2 design) and a live evidence artifact,
      `evidence/live-cold-gate.md`, on Sena 3:
      - a cold read-only `run_module` succeeds;
      - a cold `run_module(write_enabled="false")` leaves the session read-only;
      - a write attempt without `flextools_start(write_enabled=True)` is refused;
      - LCM field values are the same before and after.

      Otherwise the write gates sit behind the dispatcher and are untouched. The cold-session regression
      test (`test_mcp_tools.py:420-448`,
      `test_wire_rejected_cold_run_module_leaves_session_cold`, rewritten off
      `mcp_compat` in CP1) and the PR-0 `cold_non_readonly` golden prove a cold
      `run_module` write is still refused. CP1: one Sena 3 read smoke, never
      Claude-Swahili.
- [x] **II. Discovery Over Memory**: SDK facts come from the probes in
      research R1-R5, not memory, and the stdio test re-verifies them in CI.
- [x] **III. Self-Contained, Regenerable Extraction**: no extractor or index
      change.
- [x] **IV. Append-Only Versioned Contracts**: CP1 has no wire change and its
      major release reflects the dependency major, not the contract. CP2 is a
      minor contract bump, with nothing removed or renamed, and documents
      behavior changes in `contracts/tool-contract-1.1.md`. Floors carry a `<3`
      cap. Floors only ratchet up (sentence-transformers, research R6). Both
      checkpoints carry CHANGELOG entries.
- [x] **V. Errors That Teach**: CP1 replaces the 1.x/2.x startup guess with a
      message naming `mcp>=2.3,<3` and the exact install command. CP2 gives
      cold-session callers the real `unknown_tool`/`invalid_input` code with
      the existing guidance fields, instead of a misleading
      `session_not_initialized`. The escape hatch logs to the operations log.
- [x] **VI. One Module, One Source of Truth**: the dual registration path is
      deleted. The error-flag classifier is one shared function, which PR-E
      reuses.
- [x] **VII. Windows-First, No Cross-Platform Shims**: the deleted shim was a
      version shim, not a platform one. The suite still runs without
      FieldWorks. The stdio test needs none.
- [x] **Gate obligations scheduled**: see "Requirement -> test map". Pattern
      audit: the camelCase-read bug class (umbrella section 0, item 10, the
      latent `outputSchema` read) is swept by a permanent guard test rather
      than point fixes. No live-LCM write verification is owed (no write path).

No violations; Complexity Tracking is empty.

## Prerequisites and ordering

1. **PR-0** lands on `main` from its own branch: goldens captured on mcp 1.30
   (umbrella section 2). Then rebase `spec/mcp-modernization` onto `main`.
2. **CP1** is one PR off this branch, released as **3.0.0**.
3. Run the maintainer reinstall sequence (quickstart, "Live server").
4. **CP2** is a separate PR after CP1 merges, released as **3.1.0**.

PR-C (registry marker) is never squashed into CP1 (umbrella section 1).

## CP1 design (PR-B1)

Follow umbrella section 3 "Tasks" 1-8. Deltas from it, decided in research:

- **Floors** (R5, R6): add `jsonschema>=4.20` and raise
  `sentence-transformers>=2.3.0` alongside the mcp/pydantic/anyio changes, in
  `pyproject.toml` and `requirements.txt` identically.
- **Adapter**: per [contracts/registration-adapter.md](contracts/registration-adapter.md),
  in the new `src/flextoolsmcp/server/registration.py`. The fail-open
  pre-check is moved verbatim, including the schema-provider cache.
- **Read-only check**: `server.py`'s use of `annotation_is_read_only` becomes
  `tool_def.annotations is not None and tool_def.annotations.read_only_hint is True`.
  The `Tool(inputSchema=..., annotations=...)` constructor kwargs at
  `server.py:865-870` may stay (constructor exemption) or move to snake_case;
  pick snake_case if the SDK accepts it, for one spelling everywhere.
- **Import fallback**: the `__package__ is None` branch (`server.py:109`)
  imports `server.registration`.
- **Version-range sites** (FR-012), complete list: `pyproject.toml`,
  `requirements.txt`, `tests/conftest.py:46-99`, `tests/test_dependency_bounds.py`,
  `server/__init__.py:126,204-231` and `tests/test_lazy_loader_diagnostics.py`,
  `scripts/cap_canary.py` (`:6` stale `<2`; repoint `specs/mcp2-compat/`
  references), `.github/workflows/dep-cap-canary.yml`, `test.yml` comments,
  `publish.yml` comments, `RELEASING.md:54`, `docs/TODO.md:27`,
  `.claude/mcp-init-profile.md:44`, `CLAUDE.md:206`, and the `server.py`
  comments at `:70,:728,:853,:901,:947,:1129`.
- **CI** (R7): the `deps` axis `["lowest","latest"]` replaces `mcp` in the full
  tier; the lowest cell is installed from a `uv pip compile --resolution
  lowest-direct` lock; the downgrade step is deleted; `publish.yml` smoke does
  a stdio handshake in both eras through the console script.
- **Spec archive** (FR-017): merge `specs/mcp2-compat/{README,deferred-issues}.md`
  into `specs/_archive/mcp2-compat/` (no collisions; domain gate item 7) and
  mark drafts 1 and 4 resolved.
- **Docs** (FR-015, FR-016): CHANGELOG Breaking entry, README install notes
  (uvx `@latest`, `uv tool upgrade`, the pip pin `flextools-mcp<3`),
  RELEASING.md "Post-merge dev steps", and the conftest fail-fast message plus
  CLAUDE.md using the `uv pip install ... --python .venv\Scripts\python.exe`
  form.

## CP2 design (PR-B2)

Follow umbrella section 4. Decided here:

- **Order in `call_tool`**: `get_tool_handler(name)` -> `input_model(**arguments)`
  -> cold-session gate -> handler. The rejections before the gate return
  without calling `session_state.configure` (FR-023).
- **The gate reads validated values (write safety; plan-gate BLOCKING item).**
  Today the cold gate reads `write_enabled` and `project_name` from the raw
  `arguments` dict (`server.py:955-968`, `bool(arguments.get("write_enabled"))`).
  In CP1 that is safe only because the schema pre-check rejects
  `write_enabled: "false"` first. CP2 removes that pre-check, and Pydantic's
  lax mode would accept the string. A raw read would then turn `"false"` into
  `True` and arm writes on a cold `run_module`. CP2 MUST pass the validated
  model to the gate and read `write_enabled`/`project_name` from it.
  - Test: `test_issue53_cold_start.py::test_cold_run_module_string_false_stays_read_only`
    calls a cold `run_module(write_enabled="false")` (and `"0"`) and asserts
    `session_state.write_enabled is False`.
  - Pattern audit: grep the dispatcher for every other raw `arguments.get(`
    read and move each one to the validated model. List them in the PR body
    under "Pattern audit".
- **Classifier**: `classify_is_error(payload) -> bool` lives next to
  `error_response` in `response_utils.py`, which keeps it importable from both
  the adapter and PR-E. Rules are in data-model.md.
- **Escape hatch body**: `error_response("internal_error", ...)` with the
  `server.py:1058-1070` fields. Tracebacks stay (Q15 deferred).
- **Contract**: `CONTRACT_VERSION = "tool-responses/1.1"` plus the
  TOOL-CONTRACT.md section from [contracts/tool-contract-1.1.md](contracts/tool-contract-1.1.md).
- **Parity audit**: new `tests/test_validation_parity.py` runs every tool's
  `input_schema` (jsonschema) and its `input_model` against {extra key,
  coercible wrong type, missing required}, and reports differing verdicts.
  Session-independent tools, including `FlexToolsStartInput`
  (`extra="allow"`), get their own expected table.

## Requirement -> test map

| FR | Proving test (new unless noted) | CP |
|---|---|---|
| FR-001 | `test_dependency_bounds.py`: `mcp` floor `2.3.0`, `<3` cap, 1.x excluded; pydantic and anyio floors; pyproject == requirements | 1 |
| FR-002 | `test_dependency_bounds.py`: `jsonschema` declared in both files | 1 |
| FR-003 | `test_mcp_registration.py`: `build_server` returns `mcp.server.Server`; tool count == `len(TOOLS)` in both modes | 1 |
| FR-004 | `test_no_camelcase_mcp_reads.py` (guard regex below); `mcp_compat.py` absent | 1 |
| FR-005 | `test_mcp_registration.py`: schema-invalid args give `is_error` plus the `Input validation error` text, the handler is not called, both modes; the fail-open case (tool without a schema) | 1 |
| FR-006 | `test_mcp_registration.py::test_escaped_exception_is_error_text[legacy,auto]`: a monkeypatched `session_state.configure` raise gives `is_error` plus `Error: <exc>`, no `MCPError`; `::test_escaped_exception_logged` asserts the traceback in the temp operations log | 1 |
| FR-007 | `test_mcp_registration.py::test_adapter_passes_input_required_result` (calls `_on_call_tool` directly with a stub `call_tool_fn` returning an `InputRequiredResult`; asserts identity) and `::test_adapter_wraps_content_list` | 1 |
| FR-008 | `test_mcp_registration.py`: `server_info.version != ''`, `instructions == SERVER_INSTRUCTIONS`, both modes | 1 |
| FR-009 | `test_stdio_handshake.py` (`requires_subprocess`): handshake, list, read-only call, forced error, legacy and auto; nothing on stdout before the stream | 1 |
| FR-010 | `test_wire_goldens.py` (from PR-0), parametrized over both modes | 1 |
| FR-011 | `test_lazy_loader_diagnostics.py` (updated): hint names `mcp>=2.3,<3` and the install command | 1 |
| FR-012 | `test_dependency_bounds.py` plus a grep test: no `1.27.0` and no `mcp>=1` left in the listed sites | 1 |
| FR-013 | CI run evidence: the full-tier `lowest` and `latest` cells green; the stdio test executed in the required `test` job (log link in the PR) | 1 |
| FR-014 | publish dry run (`workflow_dispatch` on a pre-release tag, or the local quickstart step 7) | 1 |
| FR-015 | `test_dependency_bounds.py::test_release_major_matches_mcp_floor`: the package major is >= 3 whenever the mcp floor major is 2 (holds from the release commit on); CHANGELOG reviewed in PR | 1 |
| FR-016 | `test_dependency_bounds.py::test_dev_install_command_documented`: the conftest fail-fast message and CLAUDE.md both carry `uv pip install -r requirements.txt --python .venv\Scripts\python.exe`; README and RELEASING reviewed in PR | 1 |
| FR-017 | `test_dependency_bounds.py::test_mcp2_compat_spec_archived`: `specs/mcp2-compat/` is absent; `specs/_archive/mcp2-compat/README.md` and `deferred-issues.md` exist | 1 |
| FR-018 | `test_mcp_registration.py`: the adapter has no pre-check (invalid args reach the dispatcher and come back as the `invalid_input` envelope) | 2 |
| FR-019 | `test_issue243_prehandler_dispatch_envelope.py`, `test_issue53_cold_start.py` (updated): cold unknown tool gives `unknown_tool`; cold bad args give `invalid_input` | 2 |
| FR-020 | same: envelope fields `tool`, `received_arguments`, `_contract` | 2 |
| FR-021 | `test_error_flag_classifier.py`: four codes give True; others and success give False; read via nested and top-level forms | 2 |
| FR-022 | `test_mcp_registration.py` (updated): escaped raise gives the `internal_error` envelope with the `error_type`/`traceback`/`tool` order | 2 |
| FR-023 | `test_issue53_cold_start.py`: the session is still cold after an `unknown_tool` call, an `invalid_input` call to a non-read-only tool, and a cold `run_module` with bad args; plus `test_cold_run_module_string_false_stays_read_only` (CP2 design) and `evidence/live-cold-gate.md` | 2 |
| FR-024 | `test_wire_goldens.py` regenerated for the changed paths; `test_response_contract.py` reads `CONTRACT_VERSION` | 2 |
| FR-025 | `test_validation_parity.py`; the PR body lists each difference against the CHANGELOG | 2 |

**Guard** (FR-004, and the pattern audit for the camelCase-read bug class):
an AST walk over every `.py` file under `src/` and `tests/`, not a line regex.
A keyword-argument exemption on a line regex would hide reads such as
`is_error=r.isError`.

- **Flagged**:
  - an `ast.Attribute` in `Load` context whose `attr` is in the camelCase
    alias set of the mcp types;
  - a `getattr`/`hasattr` call whose string argument is in that set.

  The set is built at test time from the `mcp.types` model fields whose alias
  differs from the field name. It therefore covers `nextCursor`, `mimeType`,
  `listChanged`, `inputRequired`, all the hint fields, and any future fields.
- **Exempt by construction**:
  - `ast.keyword` names in calls (constructor kwargs);
  - dict-literal keys (raw JSON payloads such as the PR-0 goldens).
- **Sibling list**: the guard's first run is the sweep. Today's known instances
  are `test_response_contract.py:753` and the snake-case rewrite list below.
  The CP1 PR body lists them under a "Pattern audit" heading.

**Snake-case rewrites** in existing tests (from umbrella section 3 "Tests"):
`test_mcp_tools.py:203,227-270`, `test_filing_cancel.py:130-137`,
`test_parse_diff.py:337-344`, `test_parse_text_handler.py:307-314`,
`test_server_instructions.py:30-45`, and `test_response_contract.py:753` (the
latent always-`None` `outputSchema` read).

## Project Structure

### Documentation (this feature)

```text
specs/mcp2-only/
├── spec.md
├── plan.md                         # this file
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── registration-adapter.md
│   └── tool-contract-1.1.md
├── checklists/requirements.md
└── tasks.md                        # /speckit-tasks
```

### Source code touched

```text
src/flextoolsmcp/
├── mcp_compat.py                   # DELETED (CP1)
├── response_utils.py               # CP2: CONTRACT_VERSION 1.1, classify_is_error
├── server.py                       # CP1: imports, read-only check, build_server; CP2: dispatch order
└── server/
    ├── registration.py             # NEW (CP1); CP2 edits step 1 and step 3
    ├── __init__.py                 # CP1: lazy-load hint
    └── kernel.py                   # CP1: drop bare Server(...) and the unused mcp_server global (grep first)

specs/mcp2-only/evidence/
└── live-cold-gate.md               # CP2 live evidence (Sena 3); see Constitution Check I

tests/
├── test_mcp_compat.py -> test_mcp_registration.py
├── test_stdio_handshake.py         # NEW, requires_subprocess
├── test_no_camelcase_mcp_reads.py  # NEW
├── test_error_flag_classifier.py   # NEW (CP2)
├── test_validation_parity.py       # NEW (CP2)
├── conftest.py, test_dependency_bounds.py, test_lazy_loader_diagnostics.py
└── snake-case rewrites listed above

pyproject.toml, requirements.txt, pytest.ini (requires_subprocess marker)
.github/workflows/{test,publish,dep-cap-canary}.yml
scripts/cap_canary.py
docs/TOOL-CONTRACT.md (CP2), docs/TODO.md, RELEASING.md, README.md, CHANGELOG.md, CLAUDE.md
.claude/mcp-init-profile.md
specs/mcp2-compat/ -> merged into specs/_archive/mcp2-compat/
```

**Structure Decision**: single package, no new layers. The adapter is one
module that replaces the shim one-for-one.

## Risks

| Risk | Mitigation |
|---|---|
| Silent session or error-shape regression | PR-0 goldens in both eras; cold-session regression test |
| Lowest cell exposes more stale non-mcp floors | ratchet them in CP1 and record them (research R6 follow-up) |
| Windows transitive dependencies (pywin32 >=311, opentelemetry) vs pythonnet | Sena 3 read smoke before the tag |
| Stdio test flakiness on cold CI runners | 60 s timeout; pinned index dir; no update or workspace checks |
| Breaking the maintainer's live server | work off the editable install; reinstall sequence after merge |
| SDK churn inside 2.x | verified floor plus `<3` cap; the canary watches 3.x |

## Rollback

From umbrella section 10. CP1: one squash revert, ship 3.0.1 back on the
compat path, or tell users to pin `flextools-mcp==2.15.*`. CP2: revert; the
contract doc returns to 1.0.

## Complexity Tracking

None.
