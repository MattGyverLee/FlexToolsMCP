# Tasks: parser-check CP5 -- the sandbox spine

**Input**: [`plan.md`](./plan.md), [`spec.md`](./spec.md), [`research.md`](./research.md),
[`data-model.md`](./data-model.md), [`contracts/tools.md`](./contracts/tools.md),
[`contracts/hcparse.md`](./contracts/hcparse.md), [`quickstart.md`](./quickstart.md)

**Size**: `oversized`, so this is the full phased list.

**Tests**: required. The plan's test strategy gives every FR a proof and a wrong-implementation
tripwire. Tests are written first, and they must fail before the implementation that satisfies
them.

**Maintainer decisions carried in (plan, "Open maintainer decisions"):**
- **M-2**: `parse_sandbox_refused` is added. The count goes from 34 to 36.
- **M-3**: `run.json` records dispatch. Python interprets hc's output.
- **M-4**: the spec's Q2 and Q3 defaults are accepted as written: seeding from a baseline run, and
  version skew is a warning that never refuses.
- **M-1** is still open. Every live task after T094 is **`needs_human`**.

**Format**: `- [ ] **T###** [P?] [US#] Description · path`. `[P]` means the task is independent
within its wave: it touches a different file and has no incomplete dependency.

---

## Phase 1: Setup

**Wave 1 — independent (different files):**

- [x] **T001** [P] Write the scriptable fake `hc`. It prints F-3's usage text for `-h`. It reads
  the `-s` script and writes **UTF-16LE** stdout with a per-word `Parsing "..."` block (`Parse <n>`
  / `No valid parses.` / invalid segment), and `stats -p` / `stats -t` counter lines. It also prints
  `test` Expected/Actual sections (F-8). Environment knobs cover: sleep on word N, a crash mid-list,
  `Load Error:` with exit -1, a .NET host runtime-missing stderr with exit `0x80008096`, other
  usage text (not HermitCrab), and echoing the script back · `tests/fakes/hc_fake.py`
- [x] **T002** [P] Write the scriptable fake `GenerateHCConfig`. It lists its working folder to a
  side file (for FR-008), writes a config, and prints the four progress lines. Knobs cover: help
  text with exit 0, the locked message with exit 1, the migration message with exit 1, an
  unhandled crash, an empty config, N load-error lines in F-9's templates, and a slow start ·
  `tests/fakes/generate_fake.py`
- [x] **T003** [P] Create the sandbox package skeleton, with a module docstring stating the spine's
  read-only boundary · `src/flextoolsmcp/server/sandbox/__init__.py`
- [x] **T004** [P] Add the `scripts/*.ps1` package data so the wheel ships the script (FR-022) ·
  `pyproject.toml`, `MANIFEST.in`
- [x] **T005** [P] Create the packaged script skeleton for Windows PowerShell 5.1. It has the
  parameter block of contracts/hcparse.md section 2, `$script:HCPARSE_VERSION = '5.0.0'` on its own
  line (FR-024), `-Mode` dispatch, and exit 2 on a bad parameter or missing input. No PowerShell 7
  syntax · `src/flextoolsmcp/scripts/hcparse.ps1`

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T006** Add the `.cmd` shims for both fakes. Add fixtures `fake_hc`, `fake_generator`,
  `sandbox_root` (a temp `FLEXTOOLSMCP_PARSE_SANDBOX_DIR`), `fake_project` (a fake project folder
  holding `.fwdata`, `WritingSystemStore/`, `.fwdata.lock`, `.hg/`, `LinkedFiles/`, `Backups/`), and
  a `windows_only` marker · `tests/fakes/hc.cmd`, `tests/fakes/GenerateHCConfig.cmd`, `tests/conftest.py`

---

## Phase 2: Foundational (blocks every story)

**Wave 1 — independent (different files):**

- [x] **T007** [P] Add `ParserConfigFailedDetail`. Its fields, in order, are `exit_code: int | None`,
  `stderr_tail`, `log_path`, `run_id: str | None`. Add `ParseSandboxRefusedDetail` (M-2). Its fields,
  in order, are `reason` (the closed enum of contracts/tools.md section 4), `name`, `path`, `hint`,
  `needed_bytes`, `free_bytes`. Register both in `AnyDetail`, and update the docstring tally ·
  `src/flextoolsmcp/server/response_models.py`
- [x] **T008** [P] Add `ParseSandboxInput` with `extra="forbid"` and the fields of contracts/tools.md
  section 2. Validators: exactly one of `words` / `word_file` for `parse`; `words` refused for other
  actions; `from_run_id` is 32 hex characters; `limit` is `ge=1`; `timeout_seconds` is 10-86400 ·
  `src/flextoolsmcp/server/models.py`
- [x] **T009** [P] Declare the `RunMeta.spine` field (`"in_process" | "sandbox" | None`; `None` reads
  as in-process) and the `RunMeta.sandbox` field (F-12). Allow `_child` writes into `sandbox/`.
  Extend the tests: a sandbox meta survives a stage change, and a pre-CP5 fixture reads as
  `in_process` (FR-037) · `src/flextoolsmcp/server/parse/record.py`, `tests/test_parse_record.py`
- [x] **T010** [P] Write `paths.py`:
  - the root, with the `FLEXTOOLSMCP_PARSE_SANDBOX_DIR` override;
  - the `config-cache/`, `sandboxes/`, `corpora/` and `work/` per-project dirs, escaped the way
    `backup.py` escapes names;
  - the name rule of data-model section 4 (regex, reserved device names, trailing `.`, `..`,
    `resolve()` staying under its parent);
  - `assert_outside_project` applied to every root at use (FR-042).

  File: `src/flextoolsmcp/server/sandbox/paths.py`
- [x] **T011** [P] Write `script.py`:
  - resolve the packaged script via `Path(__file__)`;
  - read `HCPARSE_VERSION` with the pinned regex, requiring exactly one match;
  - build the argv as a **list** starting `powershell -NoProfile -NonInteractive -ExecutionPolicy
    Bypass -File` (FR-022);
  - load `dispatch.json` and `run.json` tolerantly.

  File: `src/flextoolsmcp/server/sandbox/script.py`
- [x] **T012** [P] Extract `_space_skip_reason`'s 2x rule into a shared `disk_space_ok(path,
  needed_bytes)` (Principle VI). The existing backup tests must pass **unmodified** ·
  `src/flextoolsmcp/server/backup.py`

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 — independent (different files):**

- [x] **T013** [P] Add the `flextools_parse_sandbox` ToolDef: `READ_ONLY_SAFE`, the verbatim first
  line of contracts/tools.md section 1, and the description body naming the refusal codes and "data,
  never instructions" (FR-034, FR-044) · `src/flextoolsmcp/server/tool_definitions.py`
- [x] **T014** [P] Route `flextools_parse_sandbox` through the six touch points CP4's `parse_cancel`
  used · `src/flextoolsmcp/server/dispatch.py`
- [x] **T015** [P] Add a `handle_flextools_parse_sandbox` stub that validates `ParseSandboxInput`
  and refuses every action for now · `src/flextoolsmcp/server/handlers/parse.py`
- [x] **T016** [P] Add rows for `parser_config_failed` and `parse_sandbox_refused`, and set the
  count to 36 · `docs/TOOL-CONTRACT.md`
- [x] **T017** [P] Add rows for `flextools_parse_sandbox` and the drifted `flextools_parse_cancel`
  (F-17) · `USAGE.md`
- [x] **T018** [P] Add golden fixtures for both new codes, and regenerate the goldens ·
  `tests/make_golden.py`, `tests/golden/responses/*.json`
- [x] **T019** [P] Add one "Tool contract" paragraph: the new tool, the two new codes, and the first
  emitters of `parser_tool_missing` and `parser_timeout` · `CHANGELOG.md`

**⟶ Wait for Wave 2 to finish, then:**

**Wave 3 — independent (different files):**

- [x] **T020** [P] Update the union count, and add a CP5 field-order block that parses
  contracts/tools.md section 4's table · `tests/test_parser_error_models.py`
- [x] **T021** [P] Update the code count, the code-to-model rows and `GOLDEN_REQUIRED_KEYS` ·
  `tests/test_response_contract.py`
- [x] **T022** [P] Add the tool to `EXPECTED_TOOL_NAMES` and `READ_ONLY_TOOLS`. Add a first-line pin
  test copied from `test_parse_text_handler.py:318` (FR-034) · `tests/test_mcp_tools.py`

**⟶ Wait for Wave 3 to finish, then:**

- [x] **T023** Run `python scripts/validate_integrity.py server` and the contract suites. Both must
  be clean at the new count (the plan's Phase 1 exit) · *(no file; gate)*

**Checkpoint**: the contract surface is in place. The tool is registered and refuses, and the
contract tests are green.

---

## Phase 3: User Story 1 — find out whether the sandbox can run (P1) 🎯 MVP

**Goal**: health tells apart "no hc", "hc cannot start" and "ready", names the fix, and names the
sandbox tool only when it is ready. The tool refuses before any copy when a component is missing.

**Independent Test**: health against three fixtures (no hc; an hc whose runtime is missing; a working
fake hc) gives the right status, component detail and hint. The tool refuses with
`parser_tool_missing`, and `work/` is unchanged.

### Tests (write first; they must fail)

**Wave 1 — independent (different files):**

- [x] **T024** [P] [US1] Discovery tests (FR-001..FR-004):
  - each of the four sources in isolation finds hc, and the `source` is recorded;
  - `.dotnet\tools\hc.exe` is found with PATH lacking it (US1 scenario 2);
  - a missing override does not fall through;
  - other usage text gives `not_hermitcrab`;
  - a host-failure stderr gives `starts=False, signal=runtime_missing`, with a reason naming the
    runtime;
  - an SDK-less `dotnet tool list` failure plus a direct hit gives found;
  - the `.dll` form runs as `dotnet hc.dll`.

  File: `tests/test_sandbox_discovery.py`
- [x] **T025** [P] [US1] Version tests (FR-005): all three versions are reported; a skewed fixture
  gives `hc_engine_version_skew` and still `ready` · `tests/test_sandbox_versions.py`
- [x] **T026** [P] [US1] Extend the no-floor regression test: an absurd version of any of the three
  still reports `ready` · `tests/test_parser_probe.py`
- [x] **T027** [P] [US1] Health-block tests:
  - the additive `sandbox` and `detected` keys;
  - `ready` names `flextools_parse_sandbox` with usable `args`;
  - each `unavailable` variant never names it (FR-006, SC-002);
  - the new next-step rungs for cannot-start and GenerateHCConfig missing;
  - swap `test_the_sweep_would_catch_a_nonexistent_tool` to a name guaranteed unregistered.

  File: `tests/test_parser_health_block.py`
- [x] **T028** [P] [US1] R-04 narrowing: permit exactly `[<hc>, "-h"]` and `[dotnet, <hc.dll>, "-h"]`.
  Add a pin that discovery never passes `-i`, `-s` or `-o` and never runs GenerateHCConfig. Give the
  fake `subprocess.run` usage-text stdout for the `-h` shape · `tests/test_cp1_boundary.py`
- [x] **T029** [P] [US1] FR-007 refusal tests:
  - a missing or non-starting hc gives `parser_tool_missing` with fields in order;
  - `install_hint.startswith("dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool")`,
    followed by exactly one sentence;
  - the GenerateHCConfig hint;
  - the `work/` root is unchanged (a boom-stub on any copy);
  - GenerateHCConfig is not required for a named-sandbox source.

  File: `tests/test_sandbox_handler.py`

### Implementation

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T030** [US1] Give `discover_hc_tool` the four ordered sources with a recorded `source`, and
  accept both the `.exe` and `.dll` forms. Add the `hc -h` probe: stdin closed, 5 s, stdout decoded
  UTF-16LE, stderr decoded UTF-8, with R-03's classification table and the `Framework:` line parsed.
  Memoise on `(path, size, mtime_ns)`. Add `SANDBOX_SIGNAL_RUNTIME_MISSING` and
  `SANDBOX_SIGNAL_NOT_HERMITCRAB`, kept outside `CLOSED_SIGNALS`. Give
  `_find_hc_via_dotnet_tool_list` an explicit encoding (pattern-audit sweep 4, known instance) ·
  `src/flextoolsmcp/server/parser_probe.py`

**⟶ Wait for T030, then:**

- [x] **T031** [US1] Read versions through Win32 `GetFileVersionInfoW` via `ctypes`:
  - the hc tool version from the tool-store path, the `dotnet tool list` row, or the dll beside it;
  - FieldWorks' HermitCrab from `get_resolved_fieldworks_dir()`;
  - GenerateHCConfig's own version.

  Compute the skew flag. It is never compared to a floor (FR-005) ·
  `src/flextoolsmcp/server/parser_probe.py`

**⟶ Wait for T031, then:**

- [x] **T032** [US1] Add the `parser.sandbox` block (status, components, advisories) and the
  `detected` keys of data-model section 7. Add contracts/tools.md section 6's rungs to
  `_build_parser_next_steps`. Replace the docstring rule at `:366` with FR-006's rule ·
  `src/flextoolsmcp/server/handlers/diagnostic_health.py`

**⟶ Wait for T032, then:**

- [x] **T033** [US1] Implement check-order steps 1-3 for `flextools_parse_sandbox`: resolve the
  project, resolve the config source (name validation only; existence arrives in US3), then
  discovery. Emit `parser_tool_missing` with the verbatim `hc` install hint (FR-007). Every refusal
  carries a `next_step` with `est_cost` · `src/flextoolsmcp/server/handlers/parse.py`

**Checkpoint**: US1 works on its own. S1 is observable on this machine now, and
`TestIntegrationWindowsFieldWorksNoHcTool` is green.

---

## Phase 4: User Story 2 — parse words against the exported grammar, safely (P1)

**Goal**: a minimal copy, cached generation judged from output, hc run under a timeout with
streamed UTF-16 output, exactly one result per word, the copy always deleted, and the result stored
as a normal run record.

**Independent Test**: parse a list of non-Latin, apostrophe, both-quotes and known-failure words
against the fakes. The per-word results are correct. The fake project folder hashes identically
before and after. `work/` is empty.

### Tests (write first; they must fail)

**Wave 1 — independent (different files):**

- [x] **T034** [P] [US2] Script invariants (Windows-only; contracts/hcparse.md section 7), for the
  Generate and Parse modes:
  - allowlist-only copy, with no `*.lock`, `.hg` or `LinkedFiles` (FR-008);
  - `-WorkDir` empty after success, generator failure, timeout and hc start failure (FR-011);
  - `-ConfigOut` under `sandboxes` exits 3 and writes nothing (FR-026);
  - quoting: `'` gives `"..."`, `"` gives `'...'`, both gives `sent:false`, and tab/CR/LF are
    handled (FR-013);
  - the `-Words "a,b c"` split and a UTF-8 no-BOM script, checked by bytes (FR-014);
  - a UTF-16 non-Latin round trip;
  - on timeout, `hc-stdout.txt` keeps every pre-kill line and `in_flight_index` is set (FR-020);
  - the console output is ASCII (FR-021);
  - no `Program Files` or `LOCALAPPDATA` literal (FR-002);
  - no `-Command` or `Invoke-Expression` (FR-022);
  - `HCPARSE_VERSION` appears once;
  - no `-o` or `-c` is passed to hc.

  File: `tests/test_sandbox_script.py`
- [x] **T035** [P] [US2] Engine-check tests (FR-036):
  - an XAmple `.fwdata` fixture is refused before the copy (boom-stub);
  - an absent or unparseable `ActiveParser` fails safe to a refusal, with the "could not be read"
    hint;
  - one retry happens on a read error;
  - there is no `flexicon` or LCM import on the path (a `sys.modules` check);
  - the result is cached in `key.json`.

  File: `tests/test_sandbox_engine.py`
- [x] **T036** [P] [US2] Workdir tests (FR-008, FR-011):
  - the allowlist measure;
  - the marker's contents;
  - the copy root is outside the project;
  - a parametrised terminal path (success, generator fail, hc load fail, timeout, cancel, a client
    exception) leaves `work/` empty;
  - a retried delete, and `cleanup: failed` recorded with the path.

  File: `tests/test_sandbox_workdir.py`
- [x] **T037** [P] [US2] Cache tests:
  - FR-009's five fixtures (help exit 0, locked, migration, crash, empty config) each give
    `parser_config_failed`, with fields in order, the log captured whole, and `stderr_tail` ASCII,
    at most 20 lines and at most 4 KiB;
  - a generation timeout gives `exit_code: null`;
  - FR-010: 3 load-error lines give `load_error_count=3`, the kinds tagged, and the run proceeds;
    the count is carried on a warm run too;
  - FR-024: the key recipe; bumping the version changes the key;
  - the per-key lock builds once under two concurrent jobs;
  - the `.partial` rename;
  - SC-006 offline: a slow fake generator is skipped on the second run;
  - FR-026: an AST pin that only `cache.build_entry` passes `-ConfigOut`, plus invalidation.

  File: `tests/test_sandbox_cache.py`
- [x] **T038** [P] [US2] Output-parser tests (FR-016..FR-019):
  - block splitting;
  - `No valid parses.` gives not_parsed;
  - an invalid segment gives its position;
  - the `stats -p` counters, and a mismatch fixture gives `counter_divergences` with neither side
    overwritten;
  - exit -1 with `Load Error:` gives zero results;
  - columns: an empty form and a space in a gloss are `readable:false` with `raw` kept, and an
    astral character reads correctly (a code-point-width parser fails this);
  - `?` for an empty gloss.

  File: `tests/test_sandbox_hc_output.py`
- [x] **T039** [P] [US2] Parse-outcome tests: every `outcome` enum value, from fixtures (FR-018).
  `parsed` is true only for `parsed` · `tests/test_sandbox_classify.py`
- [x] **T040** [P] [US2] Client tests (FR-020, FR-023, FR-035, SC-004, SC-008), driving a real
  `_execute_run` against the fakes:
  - streaming advances `words_completed` live;
  - a sleep on word 41 of 100 gives `parser_timeout` (fields in order), `words_completed=40`, the
    in-flight word named, 40 `results.jsonl` lines, and the tree killed;
  - a cancel through `flextools_parse_cancel` kills the tree;
  - a crash mid-list gives `error_no_output` plus `not_reached`, never `not_parsed`;
  - a randomised invariant: words sent equals results;
  - two concurrent jobs get distinct clients and copies;
  - an AST check that the client never reads the script's stdout for data;
  - the Python watchdog at `TimeoutSeconds + 30`.

  File: `tests/test_sandbox_client.py`
- [x] **T041** [P] [US2] Parse-action handler tests:
  - FR-015: NFC dedup, count then alphabetical order, `limit` after ordering, `truncated_by_limit`;
  - a `word_file` inside a project folder gives `word_file_invalid`;
  - FR-040: the three verdicts each give `shared_mode_unverifiable` plus its note;
  - FR-041: `next_step.est_cost` on every variant, with failure, timeout and load errors pointing to
    `flextools_grammar_health`;
  - FR-044: instruction-like words are echoed only inside data fields;
  - `results_label` is always present;
  - the response keys of contracts/tools.md section 5.1.

  File: `tests/test_sandbox_handler.py`
- [x] **T042** [P] [US2] Project-write tests (FR-042, FR-043, SC-001):
  - every root and override set inside a fake project is refused;
  - the fake project folder hashes identically across a full fake run, asserted per terminal path
    together with an empty `work/`.

  File: `tests/test_sandbox_no_project_writes.py`

### Implementation

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 — independent (different files):**

- [x] **T043** [P] [US2] Implement Generate mode:
  - copy the allowlist (`<name>.fwdata` plus `WritingSystemStore\**`) into `-WorkDir`;
  - run the generator under `-GenerateTimeoutSeconds`, with stdout and stderr captured verbatim to
    `generate-config.log`;
  - refuse a `-ConfigOut` under `sandboxes` with exit 3;
  - write `run.json`'s `generate` section;
  - clear `-WorkDir` in `finally`;
  - use exit codes 0, 4 and 6 per contracts/hcparse.md section 3.

  File: `src/flextoolsmcp/scripts/hcparse.ps1`
- [x] **T044** [P] [US2] Write `engine.py`:
  - stream-read the live `.fwdata` read-only with `FileShare.ReadWrite`;
  - `iterparse` stops at the first `MoMorphData` `rt`;
  - pass `ParserParameters` to `summarize_parser_parameters`;
  - one retry, and fail safe to XAmple with the "could not be read" hint;
  - never import LCM (R-02).

  File: `src/flextoolsmcp/server/sandbox/engine.py`
- [x] **T045** [P] [US2] Write `workdir.py`:
  - measure the allowlist size;
  - create `work/<run_id>/` with the marker;
  - delete with 3 retries 200 ms apart, recording `cleanup` and `path_if_failed`;
  - assert the delete target is under `work/` (data-model section 1).

  File: `src/flextoolsmcp/server/sandbox/workdir.py`
- [x] **T046** [P] [US2] Write `hc_output.py`, the single parser of hc's format:
  - block splitting on `Parsing "..."` headers;
  - outcomes: parsed / not_parsed / invalid_segment / error_no_output;
  - the load-banner strip for `hc-output.txt`;
  - R-08's column recovery with the UTF-16 round-trip proof;
  - parsing `stats -p` counters.

  File: `src/flextoolsmcp/server/sandbox/hc_output.py`
- [x] **T047** [P] [US2] Write the parse-outcome mapping into the `results.jsonl` sandbox line
  (data-model section 6.4): `signature: null`, `rendered_morphs` = forms, `morphs`, `readable`,
  `raw`, `flags` · `src/flextoolsmcp/server/sandbox/classify.py`

**⟶ Wait for Wave 2 to finish, then:**

**Wave 3 — independent (different files):**

- [x] **T048** [P] [US2] Implement Parse mode:
  - read `-WordFile` with `Get-Content -Encoding UTF8`, and split `-Words` on `[,\s]+` (H11,
    verbatim);
  - apply R-09's quoting and not-expressible rule, and flag a leading `-` as
    `leading_dash_unverified`;
  - write `dispatch.json` before hc starts;
  - write `hc-script.txt` as UTF-8 with no BOM, ending in `stats -p`;
  - run `System.Diagnostics.Process` with `StandardOutputEncoding = Unicode`, and write async lines
    to an `AutoFlush` UTF-8 `hc-stdout.txt` and `hc-stderr.txt`;
  - on timeout, `taskkill /T /F`, drain, and set `in_flight_index`;
  - write `run.json`'s `hc` section;
  - use exit codes 5 and 6.

  File: `src/flextoolsmcp/scripts/hcparse.ps1`
- [x] **T049** [P] [US2] Write `cache.py`:
  - the key is `sha256(canonical inputs)[:16]`, including `HCPARSE_VERSION`;
  - an `asyncio.Lock` per `(project, key)`;
  - `build_entry` runs `-Mode Generate` into `<key>.partial/`, is judged by R-05's three conditions,
    extracts load errors by exclusion list with template tags, then renames atomically;
  - `key.json` per data-model section 3;
  - lookup skips invalidated or empty entries;
  - `invalidate(project)`;
  - `last_used_at` is updated.

  File: `src/flextoolsmcp/server/sandbox/cache.py`

**⟶ Wait for Wave 3 to finish, then:**

- [x] **T050** [US2] Write `SANDBOX_ROLE` and `SandboxClient`, which implement the worker-client
  interface:
  - `start` runs the engine check (when generating), the cache lookup or build, and launches
    `-Mode Parse` for the whole list;
  - `parse_word` awaits the next block, tailed from `hc-stdout.txt` every 100 ms, and returns
    not-expressible words immediately;
  - `cancel_run` kills the tree;
  - its own `finally` deletes the copy (tree kills skip the script's);
  - the watchdog;
  - `run.json` is folded into `meta.sandbox`;
  - counters are reconciled into `counter_divergences`.

  File: `src/flextoolsmcp/server/sandbox/client.py`

**⟶ Wait for T050, then:**

- [x] **T051** [US2] In `start_run`, when `worker_role == SANDBOX_ROLE`, build a per-run client
  instead of calling `WorkerPool.get` (F-13). Map a timeout to a `parser_timeout` `RunFailure.detail`
  with `timeout_seconds`, `words_completed`, `run_id` and `hint`. Map an hc start failure to
  `parser_job_failed` (`crashed`) · `src/flextoolsmcp/server/parse/runner.py`

**⟶ Wait for T051, then:**

- [x] **T052** [US2] Implement the `parse` action through check-order steps 4, 5 and 8:
  - the engine check before any file is created;
  - `probe_project_access`, which only sets staleness on `SANDBOX_STALENESS_VERDICTS` (R-13);
  - FR-015 ordering and `words.txt`;
  - `start_run(worker_role=SANDBOX_ROLE)` with the fast path or a run id;
  - the section 5.1 envelope: `spine`, `config_source`, `versions`, `advisories`, `generation`,
    `results_label`, and `next_step` with `est_cost`;
  - `scope_fingerprint` with `scope_kind="words"` and `engine="HC"` (R-14).

  File: `src/flextoolsmcp/server/handlers/parse.py`

**⟶ Wait for T052, then:**

**Wave 7 — independent (different files):**

- [x] **T053** [P] [US2] In `after_terminal`, invalidate the project's sandbox cache beside
  `mark_read_worker_stale` (FR-026) · `src/flextoolsmcp/server/filing/observer.py`
- [x] **T054** [P] [US2] After a write-enabled `run_module` completes without error, invalidate the
  cache through a **lazy, guarded** import in a try/except, logged and never propagated. A read-only
  run does not invalidate. `test_issue55_write_safety_ladder.py` and the `run_module` suites must
  pass unmodified · `src/flextoolsmcp/server/handlers/execution.py`
- [x] **T055** [P] [US2] Add `server/sandbox/*.py` to the standing no-writes scan ·
  `tests/test_parse_no_project_writes.py`
- [x] **T056** [P] [US2] Add `server/sandbox/*.py` to the no-edit-blocking scan ·
  `tests/test_parse_no_edit_blocking.py`
- [x] **T057** [P] [US2] Delete the root-level contributed script (its history stays in git) and
  update its references · `hcparse.ps1`, `scripts/ralph/campaign.json`

**Checkpoint**: US1 and US2 work. A word list parses end to end against the fakes, with a run id,
status, cancellation and a byte-identical project.

---

## Phase 5: User Story 3 — rehearse a grammar edit in a named sandbox (P1)

**Goal**: create a user-owned, editable copy of the exported config, run against it, and never let
cache logic touch it.

**Independent Test**: create a sandbox, edit it, run words against it, then invalidate, rebuild
and prune the cache. The sandbox bytes are identical, and a second create with the same name is
refused.

### Tests (write first; they must fail)

**Wave 1 — independent (different files):**

- [x] **T058** [P] [US3] Sandbox store tests (FR-028, FR-029):
  - a path is returned and `origin.json` is recorded;
  - a second create is refused and the **first file is byte-identical**;
  - `..`, separators, `CON`, `con.txt`, empty, too-long and trailing-`.` names are refused;
  - `edited` comes from sha256;
  - after a project stat change, `predates_project_grammar` is set and the sandbox bytes are
    unchanged.

  File: `tests/test_sandbox_store.py`
- [x] **T059** [P] [US3] Lifecycle tests (FR-025, SC-007): prune, invalidate and rebuild leave
  sandbox and corpus bytes identical. An AST check confirms every deleter in `cache.py` and
  `workdir.py` guards its root, and that no function there accepts a `sandboxes/` or `corpora/`
  path · `tests/test_sandbox_lifecycles.py`
- [x] **T060** [P] [US3] Sandbox handler tests:
  - `create_sandbox` builds a cache entry first when none is usable, synchronously, and a generation
    failure gives `parser_config_failed` with `run_id: null`;
  - `sandbox_exists` and `sandbox_not_found`;
  - a run against a sandbox skips the engine check and does not require GenerateHCConfig;
  - the `sandbox_predates_project_grammar` advisory;
  - a broken sandbox XML gives `parser_job_failed` with hc's `Load Error:` and zero parse results
    (US3 scenario 5);
  - `list`.

  File: `tests/test_sandbox_handler.py`

### Implementation

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T061** [US3] Write the sandbox half of `store.py`:
  - create with an exclusive-create open, never `"w"`, copying the entry's `hc-config.xml`;
  - write `origin.json` once;
  - `list`;
  - derive `edited` and `predates_project_grammar` from a `stat` alone, never opening the project.

  File: `src/flextoolsmcp/server/sandbox/store.py`

**⟶ Wait for T061, then:**

- [x] **T062** [US3] Implement the `create_sandbox` and `list` actions (contracts/tools.md sections
  5.2 and 5.4). Add the named-sandbox config source to check-order step 2, with existence checks and
  `config_source: {"kind": "named_sandbox", ...}` in the meta. Add the predates advisory ·
  `src/flextoolsmcp/server/handlers/parse.py`

**Checkpoint**: US3 works. A sandbox can be made, edited and run, and it survives every cache
operation.

---

## Phase 6: User Story 4 — corpus assertions: regressions vs new ambiguity (P2)

**Goal**: seed a corpus from a baseline run, run it with `hc test`, and classify each assertion from
the Expected and Actual sections into pass / regression / new_ambiguity / changed / error.

**Independent Test**: seed from a fake baseline. Configure the fake so word A loses its parse and
word B gains one. Exactly one `regression` and one `new_ambiguity` result, each listing the right
parse, and the totals equal `stats -t`.

### Tests (write first; they must fail)

**Wave 1 — independent (different files):**

- [x] **T063** [P] [US4] Test-mode script tests (FR-027):
  - each assertion is emitted as `test -p <f:g|f:g> ... "<word>"`;
  - each of `| : \ ' "` and whitespace, and an empty parse, gives `sent:false` with its reason;
  - the dispatch never contains `\` (F-5);
  - an empty gloss is written as `?`;
  - the script ends in `stats -t`.

  File: `tests/test_sandbox_script.py`
- [x] **T064** [P] [US4] Classification tests (FR-031..FR-033, SC-005):
  - the four-way table from F-8 fixtures;
  - `expected: []` that now parses gives `new_ambiguity` with `label: "now_parses"`;
  - a text scan finds "fixed" nowhere;
  - buckets: regression goes to broken, new_ambiguity and changed go to changed, pass goes to
    unchanged, error goes to not_compared.

  File: `tests/test_sandbox_classify.py`
- [x] **T065** [P] [US4] Output-parser tests for the `test` Expected/Actual sections, the `stats -t`
  counters, and the reconciliation table of data-model section 6.6 · `tests/test_sandbox_hc_output.py`
- [x] **T066** [P] [US4] Corpus store tests (FR-030):
  - parsed words keep their exact readable parses in hc's order;
  - `not_parsed` becomes `[]`;
  - other outcomes are excluded and listed with a reason;
  - an in-process, incomplete or test-mode run gives `run_not_seedable`;
  - `corpus_exists`;
  - `corpus_invalid` names the JSON path of the first fault;
  - NFC duplicates are de-duplicated, keeping the first.

  File: `tests/test_sandbox_store.py`
- [x] **T067** [P] [US4] Handler tests for `seed_corpus` (its check order; synchronous; no run) and
  `run_corpus` (step 6 corpus load; summary counts by classification; `hc_counters`;
  `counter_agreement`) · `tests/test_sandbox_handler.py`

### Implementation

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 — independent (different files):**

- [x] **T068** [P] [US4] Implement Test mode: read `-AssertionFile`, apply FR-027's check, emit
  `-p` values as `form:gloss` with no exceptions, add `--` only for a leading-`-` word, and end the
  script with `stats -t` · `src/flextoolsmcp/scripts/hcparse.ps1`
- [x] **T069** [P] [US4] Parse the `Testing "..."` blocks, the `Expected parses:` / `Actual parses:`
  sections (`None` or unmatched parses) and the `stats -t` counters ·
  `src/flextoolsmcp/server/sandbox/hc_output.py`
- [x] **T070** [P] [US4] Write the assertion classification and the `now_parses` label, the
  diff-bucket mapping, and the assertion line of data-model section 6.5 ·
  `src/flextoolsmcp/server/sandbox/classify.py`
- [x] **T071** [P] [US4] Write the corpus half of `store.py`: seed from a completed sandbox parse
  run, with an exclusive create; load and validate the whole file per data-model section 5 ·
  `src/flextoolsmcp/server/sandbox/store.py`

**⟶ Wait for Wave 2 to finish, then:**

- [x] **T072** [US4] Add Test mode to `SandboxClient`: launch `-Mode Test`, return assertion lines,
  reconcile `stats -t` against the classifications, and record `counters: "unavailable_timeout"` on
  a timeout · `src/flextoolsmcp/server/sandbox/client.py`

**⟶ Wait for T072, then:**

- [x] **T073** [US4] Implement the `seed_corpus` action (contracts/tools.md sections 3 and 5.3) and
  the `run_corpus` action, including check-order step 6 and the `meta.sandbox.corpus` record ·
  `src/flextoolsmcp/server/handlers/parse.py`

**⟶ Wait for T073, then:**

- [x] **T074** [US4] Make the diff read assertion lines through the bucket mapping. `new_ambiguity`
  is never unchanged (FR-032). Extend the diff tests to cover this ·
  `src/flextoolsmcp/server/parse/diff.py`, `tests/test_parse_diff.py`

**Checkpoint**: US4 works. A corpus run separates regressions from new ambiguity.

---

## Phase 7: User Story 5 — diagnose a sandbox run afterwards (P2)

**Goal**: the log tool fills `config_generation`, `hc_stdout` and `hc_output` for sandbox runs.
In-process responses are unchanged. The diff states cross-spine comparisons plainly.

**Independent Test**: four fake sandbox runs (success, load errors, timeout, broken sandbox). Every
section is real content or a typed not-applicable answer, and none is empty. In-process log
responses match today's golden byte for byte.

### Tests (write first; they must fail)

**Wave 1 — independent (different files):**

- [x] **T075** [P] [US5] Log-section tests (FR-038, SC-009):
  - the four-run matrix, with every section real or typed;
  - a warm run's reuse line in `config_generation`, and `load_errors` itemised and counted;
  - an empty file gives `_empty_note`;
  - in-process responses byte-identical to today;
  - `summary.run_spine` read from the meta.

  File: `tests/test_parse_log_sections.py`
- [x] **T076** [P] [US5] Diff tests (FR-039, FR-040):
  - a sandbox against an in-process run diffs, `comparison.note` names the two engines, and the
    form-only comparison is disclosed;
  - sandbox against sandbox compares `(form, gloss)`;
  - `no_change` becomes `no_change_unverifiable` when **either** run carries
    `shared_mode_unverifiable`;
  - CP3's in-process verdicts are unchanged.

  File: `tests/test_parse_diff.py`

### Implementation

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 — independent (different files):**

- [x] **T077** [P] [US5] Make `parse_log` spine-aware. Applicability comes from `meta.spine`. The
  three sections are served from `sandbox/generate-config.log`, `hc-stdout.txt` and `hc-output.txt`,
  with `_empty_note` for empty files. The in-process path is left byte-identical ·
  `src/flextoolsmcp/server/handlers/parse.py`
- [x] **T078** [P] [US5] Add the `comparison` block (`same_spine`, `same_config_source`,
  `same_engine_version`, `note`). Add the additive either-run staleness downgrade, and leave
  `shared_mode_active` unchanged (R-13) · `src/flextoolsmcp/server/parse/diff.py`
- [x] **T079** [P] [US5] Force `RENDERED_FALLBACK` for any cross-spine pair, and use `morphs` for
  sandbox-to-sandbox pairs. Settle R-14's `[CHECK]` on the auto-selection at `:129-173` ·
  `src/flextoolsmcp/server/parse/signature.py`

**⟶ Wait for Wave 2 to finish, then:**

- [x] **T080** [US5] Make `parse_status` name `in_flight` (the word) and `words_completed` on a
  sandbox timeout, and include data-model section 6.6's summary (SC-008) ·
  `src/flextoolsmcp/server/handlers/parse.py`

**Checkpoint**: US5 works. Every sandbox run can be diagnosed afterwards.

---

## Phase 8: User Story 6 — keep disk use bounded (P3)

**Goal**: refuse a run without room for its copy, sweep orphaned copies, and prune the cache to 3
entries per project.

**Independent Test**: 30 fake runs, including killed ones. No copy remains, at most 3 cache entries
remain per project, and run retention holds.

### Tests (write first; they must fail)

**Wave 1 — independent (different files):**

- [x] **T081** [P] [US6] Free-space and sweep tests:
  - FR-012: a patched `disk_usage` below 2x the **allowlist** size refuses with `needed_bytes` and
    `free_bytes`, and no directory is created;
  - FR-011: the sweep removes a marked orphan whose run is not live, and ignores unmarked dirs and
    live runs.

  File: `tests/test_sandbox_workdir.py`
- [x] **T082** [P] [US6] Prune tests: keep 3 per project in LRU order; an in-use (refcounted) entry
  survives; invalidated entries are deleted at refcount 0 · `tests/test_sandbox_cache.py`
- [x] **T083** [P] [US6] A 30-run soak against the fakes, including killed runs. Afterwards `work/`
  is empty, at most 3 cache entries remain, and retention holds · `tests/test_sandbox_client.py`

### Implementation

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 — independent (different files):**

- [x] **T084** [P] [US6] Add a free-space check through the shared `disk_space_ok`, over the
  allowlist size and the `work/` volume. Add the marker sweep ·
  `src/flextoolsmcp/server/sandbox/workdir.py`
- [x] **T085** [P] [US6] Add an LRU prune to 3 per project, with an in-process refcount and deletes
  guarded to `config-cache/` · `src/flextoolsmcp/server/sandbox/cache.py`

**⟶ Wait for Wave 2 to finish, then:**

- [x] **T086** [US6] Wire the lifecycle steps into the handler:
  - check-order step 7 refuses with `parse_sandbox_refused` (`insufficient_disk_space`) on a cache
    miss only;
  - the sweep runs before a server's first sandbox job;
  - the prune runs at each job start.

  File: `src/flextoolsmcp/server/handlers/parse.py`

**Checkpoint**: all six stories work on their own.

---

## Phase 9: Polish and cross-cutting

**Wave 1 — independent (different files):**

- [x] **T087** [P] Add the sandbox `next_step` rows to section 10.2, the F-1 and R-04 notes under
  section 13 H1/H4, and the new codes to section 14 · `specs/parser-check/SPEC.md`
- [x] **T088** [P] Correct the Assumptions bullet on the engine check: it reads the live file as a
  stream, before the copy, never through LCM (R-02) · `specs/parser-check-cp5/spec.md`
- [x] **T089** [P] Add section 11: `spine`, `sandbox`, the `sandbox/` files, and the `outcome` and
  `assertion` keys · `specs/parser-check-cp3/contracts/artifact.md`
- [x] **T090** [P] Turn the `CP4-Scratch-` prefix into a parameter, so CP5 can use `CP5-Scratch-` ·
  `tests/live_support/make_disposable.py`
- [x] **T091** [P] Write the live harness. It is marked `requires_flex`, fails under
  `FLEXLIBS_REQUIRE_LIVE=1` and skips otherwise. It takes a byte-identity hash on every scenario and
  records the three versions in each evidence file. It covers S1-S13 and L-1-L-7 ·
  `tests/test_parse_live_cp5.py`

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T092** Run the five pattern-audit sweeps from the plan:
  1. trusting a subprocess exit code;
  2. cleanup on the happy path only;
  3. a verdict set that omits a member, which answers R-13's in-process question;
  4. an implicit subprocess encoding;
  5. a typed reader that drops keys.

  Record every sibling (file:line, confidence, fixed or intended) for the commit body. Apply fixes
  where the sweep finds a real sibling · `specs/parser-check-cp5/reviews/pattern-audit.md`

**⟶ Wait for T092, then:**

- [x] **T093** Validate against the Success Criteria (SC-010). Run the full `pytest` suite, lint and
  pre-commit, and `python scripts/validate_integrity.py server`. The boundary tests and error-model
  field-order tests must stay green · *(no file; suite run)*

**⟶ Wait for T093, then:**

- [x] **T094** Run the live checks that work on this machine now: S1 (no hc: health and the
  refusal), and the "before" half of L-5 if an hc 3.8 binary can be obtained without installing
  anything · `specs/parser-check-cp5/evidence/s1-health-no-hc.json`

**⟶ Wait for T094, then:**

- [ ] **T095** **[needs_human, blocked on M-1]** Run L-1..L-7 and S2..S13 against a working hc. Fold
  the answers back into code: the allowlist in `workdir.py`, the leading-dash rule, the BOM
  handling, the timeout default, and the runtime matcher in `parser_probe.py`. Record SC-003 as
  "partially verified (version-skewed)" on the no-SDK route. With no hc and no human, stop as
  `needs_human`, and never downgrade to mocks · `specs/parser-check-cp5/evidence/*.json`

---

## Dependencies & Execution Order

**Phase order**: Setup (1) → Foundational (2) → US1 (3) → US2 (4) → US3 (5) → US4 (6) → US5 (7) →
US6 (8) → Polish (9).
- US1 and US2 are the MVP.
- US3 needs US2's cache and client.
- US4 needs US2's client and US3's store module.
- US5 needs sandbox runs to exist (US2) and assertion lines (US4) for its full matrix.
- US6 needs US2's workdir and cache.
- `handlers/parse.py` is edited in every story phase, so those edits never share a wave.

**Waves per phase:**
- **Phase 1**: W1 (T001-T005) → T006.
- **Phase 2**: W1 (T007-T012) → W2 (T013-T019) → W3 (T020-T022) → T023 gate.
- **Phase 3 (US1)**: tests W1 (T024-T029) → T030 → T031 (same file) → T032 → T033.
- **Phase 4 (US2)**: tests W1 (T034-T042) → W2 (T043-T047) → W3 (T048, T049) → T050 → T051 → T052 →
  W7 (T053-T057).
- **Phase 5 (US3)**: tests W1 (T058-T060) → T061 → T062.
- **Phase 6 (US4)**: tests W1 (T063-T067) → W2 (T068-T071) → T072 → T073 → T074.
- **Phase 7 (US5)**: tests W1 (T075, T076) → W2 (T077-T079) → T080.
- **Phase 8 (US6)**: tests W1 (T081-T083) → W2 (T084, T085) → T086.
- **Phase 9**: W1 (T087-T091) → T092 → T093 → T094 → T095 (needs_human).

**Blocking notes:**
- Phases 1-8 and T087-T094 are entirely offline and are **not** blocked on M-1.
- T095 is the only task blocked on M-1.
- Overturning M-2 changes T007, T016, T018 and T020-T022.
