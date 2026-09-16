# Tasks -- parser-check, CP1

**Spec:** [`SPEC.md`](./SPEC.md) | **Plan:** [`plan.md`](./plan.md) |
**Research:** [`research.md`](./research.md) |
**Data model:** [`data-model.md`](./data-model.md) | **Contracts:** [`contracts/`](./contracts/)

**Scope: CP1 only** (SPEC 15). No parser is constructed, no grammar is loaded into
HermitCrab, nothing is parsed; `HCParser` is touched by reflection only. Every
deliverable is `READ_ONLY_SAFE` and CP1 writes nothing.

**Line format:** `- [ ] **T###** [P?] [US#] Description · exact/file/path`.
`[P]` = independent of the other tasks in its wave (different file, no incomplete
dependency). Same-file or dependent tasks are never in the same wave.

**Numbering.** `T001`-`T028` are never renumbered -- external references point at
them. Tasks added in cycle 6 (`T029`-`T035`) keep those IDs regardless of where they
land below: IDs are stable references, but document order follows each task's
dependency position, not numeric order.

**User stories (derived from CP1's deliverables -- SPEC has no numbered stories):**

| Story | Priority | The question it answers |
|---|---|---|
| **US1** | P1 | "Before anything is parsed, is each of the three spines actually reachable on this machine?" |
| **US2** | P1 | "What in my grammar could make a parse never finish?" (`flextools_grammar_health`, SPEC 9.5.5) |
| **US3** | P2 | "Refuse rather than mislead" -- engine-mismatch and missing-HC-agent helpers. Ships with tests; its first caller arrives at CP2 |

---

## Phase 1: Setup

**Wave 1 -- independent (different files):**

- [x] **T001** [P] Create the `server/scan/` package so the subprocess-run scan module has a home · `src/flextoolsmcp/server/scan/__init__.py`
- [x] **T002** [P] Add the shared CP1 test fixtures -- fake ParserCore member sets (complete, missing `ParseFiler.ProcessParse`, foreign directory), `ParserParameters` XML variants (valid `HC`, valid `XAmple`, corrupt), and LCM grammar-object stubs (`IMoForm`, `IPhPhoneme`, `IMoInflAffixSlot`, `IPhSegmentRule` with `Disabled`) · `tests/fixtures/parser_check.py`

---

## Phase 2: Foundational (BLOCKS all stories)

The four error codes are additive at `tool-responses/1.0` (SPEC 14, research D6). The
contract rows land **before** any handler emits them.

**Wave 1 -- independent (different files):**

- [x] **T003** [P] Add the four detail models -- `ParserEngineMismatchDetail`, `ParserCoreMissingDetail`, `ParserAgentMissingDetail`, `ParserToolMissingDetail` -- with `model_config = ConfigDict(extra="forbid", populate_by_name=True)` and a `Literal` discriminator, matching the pattern from line 142 onward. Field names verbatim from [`contracts/error-codes.md`](./contracts/error-codes.md); closed enums `signal`, `component`, `probe_source` are the contract and must not be renamed, recased or extended. **Extend the `AnyDetail` Union** (`response_models.py:364-382`) to include all four new models -- otherwise `validate_detail()`'s discriminated `TypeAdapter` never sees them -- and bump the hand-maintained "18" to **22** in both the module docstring and `validate_detail()`'s own docstring (417-421), the same count T004 bumps in `TOOL-CONTRACT.md` · `src/flextoolsmcp/server/response_models.py`
- [x] **T004** [P] Add one table row per new code and change "one of the **18** codes below" to **22** (the count is hand-maintained) · `docs/TOOL-CONTRACT.md`
- [x] **T005** [P] Add the "Tool contract" entry recording the four additive codes, explicitly noting no version bump · `CHANGELOG.md`

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T006** Envelope test: each of the four detail models validates its contract example and **rejects an unknown field** (`extra="forbid"`), and each closed enum rejects a value outside its set. **Assert through `validate_detail()`**, not just the bare model class, so the shared discriminated-union validator every other code's detail payload goes through actually accepts each of the four new codes · `tests/test_parser_error_models.py`

---

## Phase 3: US1 -- parser spine preflight (P1)

**Goal.** `flextools_health` gains a `parser` block saying, per spine, whether it is
`ready` or `unavailable` and why -- without opening a project, loading a grammar, or
parsing anything.

**Independent test.** Call `flextools_health` on a machine with FieldWorks installed
and no `hc` dotnet tool: the sandbox spine reports `unavailable` with the real
`dotnet tool install` hint while the in-process spines report `ready`, and no other
spine is blanked.

### Tests

**Wave 1 -- independent (different files):**

- [x] **T007** [P] [US1] Probe tests: ParserCore resolved from a directory other than the one supplying `SIL.LCModel.dll` yields `signal=foreign_install`; a missing bound member yields `signal=incompatible_surface` naming it in `missing_members`; **an unexpected-but-complete version passes and is reported** (the standing regression test against reintroducing a version floor -- no code path may compare `detected_version`); an `Assembly.LoadFile` throw maps to `signal=load_failed` with `load_error`; the probe opens no `LcmCache` and loads no grammar · `tests/test_parser_probe.py`
- [x] **T008** [P] [US1] Health parser-block tests: exactly two states per spine (`ready`/`unavailable`, never a third `degraded`); one dead spine does not blank the other two; `read: ready` with `write: unavailable` when only `ParseFiler.ProcessParse` is absent; `agent_probe: "skipped"` is **never reported as a pass**; `active_engine` never decides a status; `next_step` never names a tool whose spine is `unavailable` and never names `flextools_try_word`, which does not exist until CP2. Also includes SPEC 16's "Integration (Windows + FieldWorks, no `hc` tool)" bullet as a named integration test: on a real machine with FieldWorks installed and no `hc` dotnet tool, the sandbox spine reports `unavailable` with the real `dotnet tool install` hint while the in-process spines report `ready`; this test is skipped automatically off Windows or without FieldWorks installed · `tests/test_parser_health_block.py`
- [x] **T032** [P] [US1] Record the D-note for why `active_engine` is unconditionally `null` at CP1 -- same premise as `agent_probe: "skipped"` (research D2: `flextools_health` never opens a project), currently asserted by T012 with no recorded decision. Gates T012's assertion · `specs/parser-check/research.md`

### Implementation

**Wave 2 (single -- new module, everything below builds on it):**

- [x] **T009** [US1] New module: `ProbeResult`, the same-install check via the existing `get_resolved_fieldworks_dir()` (recomputed per call, no binding retained) plus locating **`ParserCore.dll`** within that directory -- `get_resolved_fieldworks_dir()` returns the directory containing `SIL.LCModel.dll`, a different DLL in the same install tree, not `ParserCore.dll` itself -- and the reflective member probe over `HCParser(LcmCache)`, `Update()`, `ParseWord(string)`, `TraceWordXml(string, IEnumerable<int>)`, `ParseWordXml(string)` -- plus `ParseFiler.ProcessParse` for the write probe only. **Bind positionally, not by keyword** (`IParser` names the parameter `word`, `HCParser` implements it as `form`). `Assembly.LoadFile` throw caught and mapped to `load_failed`. **Precedent note:** `versioning.py`'s existing `Assembly.LoadFile` use (262) reads only `GetName().Version`; the member/Type-reflection precedent (`GetMembers`, generic unwrapping) lives in `liblcm_extractor.py` (~330) over different LCM interface types -- this task combines those two precedents, it does not reuse one wholesale. Invariant: `ok=True` implies `missing_members == []` and `signal is None` · `src/flextoolsmcp/server/parser_probe.py`

**⟶ Wait for T009 (same file), then:**

- [x] **T010** [US1] `hc` and `GenerateHCConfig.exe` discovery. `hc` is a **dotnet global tool** on PATH / `dotnet tool list -g` with a config override -- *not* `%LOCALAPPDATA%\HermitCrabTool\hc.dll`. The `dotnet` call runs under a **bounded timeout**: a slow or hanging call reports the component as not found with the reason recorded and never blocks the health response (SPEC open question 8, specified here). Install hint is literally `dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool` · `src/flextoolsmcp/server/parser_probe.py`

**⟶ Wait for T010 (same file), then:**

- [x] **T011** [US1] `ParserDetector` aggregate returning `read_probe`, `write_probe`, `sandbox_probe` (`{hc, generate_config}`), `agent_probe`, `active_engine` and `versions` (`parser_core_version`, `lcmodel_install_path`, `hc_tool_version`) -- the seam `diagnostic_health.py` consumes · `src/flextoolsmcp/server/parser_probe.py`

**⟶ Wait for T011 and T032, then:**

- [ ] **T012** [US1] `_build_parser_block()` shaping `ParserDetector`'s output into the new top-level `parser` key, matching `_build_fieldworks_block()`'s shape. **Composition only** -- no location or reflection logic enters this module; its "pure composition, no new detection logic" docstring is a contract other code and tests rely on. Because health never opens a project (research D2), `write.reason` records `agent_probe: "skipped"` and the status is decided by the member probe alone; `active_engine` is `null` (per T032's D-note -- same premise as `agent_probe: "skipped"`) · `src/flextoolsmcp/server/handlers/diagnostic_health.py`

**⟶ Wait for T012 (same file), then:**

- [ ] **T013** [US1] `next_step` rungs per unhealthy state, from the table in [`contracts/flextools_health-parser-block.md`](./contracts/flextools_health-parser-block.md). **CP1 degradation:** the two rows naming `flextools_try_word` degrade to `tool: null`. For the `write: unavailable`/`read: ready` row, nulling `tool` is not enough -- its action text ("use read-only Try A Word; filing unavailable") still names the tool in prose, which itself violates SPEC 10.1's "never propose a tool that does not exist." Replace that row's CP1 action text with this literal string, which names no tool: "filing is unavailable on this install; read-only parser diagnosis is unaffected." (Do not say the read spine confirms the grammar loads -- nothing at CP1 loads a grammar, so `read: ready` means only that ParserCore's read surface is reachable.) The `write: unavailable`/`signal: parser_agent_missing` row's action text does not name the tool in prose already, so `tool: null` alone suffices there. Never propose `flextools_parse_sandbox` when either sandbox component is missing · `src/flextoolsmcp/server/handlers/diagnostic_health.py`, `specs/parser-check/contracts/flextools_health-parser-block.md`

**Checkpoint.** US1 is independently functional: `flextools_health` reports all three
spines per-spine, with reasons, on a real install -- with nothing from US2 or US3
present.

---

## Phase 4: US2 -- `flextools_grammar_health` (P1)

**Goal.** The primary G4 instrument (SPEC 9.5.2): a pure-LCM static scan naming the
grammar properties that multiply search paths, costing no parse time. Standalone
value on day one -- no dependency on ParserCore, the `hc` tool, or a parse.

**Independent test.** Call the tool on a project holding a zero-surface morph: the
finding comes back with its count, its `measured` wording and `goto_url`s --
unconditional on position, since slot-reachability walking is deferred (see T034); no
parse runs; no scalar score appears at any depth.

### Tests

**Wave 1 -- independent (different files):**

- [x] **T014** [P] [US2] Response-contract tests (enforced by test, not convention -- SPEC 9.5.3, 9.5.7, research D7): **no** `score`, `grade`, `health`, `rating`, `severity`, `priority`, `rank`, `impact`, `tier`, `weight`, `urgency` or `significance` at any nesting level (the last five are renamed-proxy backstops, not the primary guard -- see below); `findings` ordered by 9.5.4 row order and **never** sorted by `count`; counts never summed into a total; the strings `invalid`, `incorrect`, `wrong`, `error`, `defect`, `broken`, `faulty`, `flawed`, `problematic`, `malformed` and `bug` never describe a finding (a G4 finding names a **suspect**); the scan reads grammar objects only and **never** `IWfiAnalysis` or wordforms (SPEC 3.1); constructs no `HCParser`; opens no `LcmCache` in the MCP server process. **Structural closure, not just name-denial:** assert the `Finding`/output model is Pydantic `extra="forbid"` with an explicit key allowlist of exactly `check_id, spec_row, count, measured, evidence_basis, objects` (see T017's `GrammarHealthFinding`), **and that `objects[]` items are closed the same way** -- `FoundObject`, `extra="forbid"`, exactly `hvo, class_name, label, goto_url` -- so "any nesting level" is enforced at every level, not just the top. **Order-invariance:** run the same checks twice with permuted count magnitudes and assert `findings` order is byte-identical both times, closing the "first finding is worst" smuggling path; assert `objects[]` item order is likewise never magnitude-sorted. **Positive check:** `measured` also matches a factual, count-based phrasing template, since a denylist alone is bypassed by synonym · `tests/test_grammar_health.py`
- [x] **T015** [P] [US2] Per-check unit tests against the T002 LCM stubs: row 1 (zero-surface `IMoForm`) reported as a suspect with its count -- and **positively assert the CP1 scope**: a zero-surface `IMoForm` reachable from *no* optional slot is still counted, because at CP1 the check is unconditional on position (the slot-reachability walk is deferred with T034); row 10 (`IMoInflAffixSlot.Optional`) -- and `IMoInflAffixSlot` is **not** `ICmPossibility`, so `ICmPossibility(obj).Name` must not appear; **disabled rules excluded before counting** (`IPhSegmentRule.Disabled`); a check whose LCM names are unverified appears in `checks_skipped` with reason `lcm_name_unverified` rather than being silently omitted; **regression guard:** a stub `IMoForm` whose `Form` is literally `"***"` is counted as zero-surface, not skipped -- this direct-LCM-read path does not get Flexicon's Operations-layer `"***"` -> `""` normalization · `tests/test_grammar_scan_checks.py`

### Implementation

**Wave 2 -- research chain, strictly ordered, same file (`research.md`), gates which checks may be written: `T016` -> `T031` -> `T029`. `T027` (`SPEC.md`) and `T033` (`data-model.md`) run alongside this chain, `[P]` -- different files, no dependency either direction:**

- [x] **T016** [US2] Verify the three outstanding LCM names against this project's index with `flextools_get_object_api` -- `IMoAffixProcess` and `IPhMetathesisRule` (rows 5 and row 3's metathesis half) and `ILexEntry.AlternateFormsOS` (row 7's second half; `IMoStemAllomorph.StemNameRA`, row 7's first half, is already verified and is not gated). **Record, per gated sub-check, the written-or-skipped verdict and the exact `checks_skipped` reason string** -- on confirmation, the sub-check becomes a written check in T034/T035; on non-confirmation, it becomes a `checks_skipped` entry with reason `lcm_name_unverified`. Never silently dropped either way · `specs/parser-check/research.md`
- [x] **T031** [US2] Research probe (reflection-only -- no type instantiation, no grammar loaded; must not trip T026's boundary scan): is `SIL.Machine.Morphology.HermitCrab.GrammarHealthChecker` public in the **installed** dll? If yes, the three PanGloss-ported lints (`hc-undeclared-segment`, `hc-duplicate-feature-bundle`, `hc-partial-morpheme`) come free -- record the verdict and either fold them into T034/T035's scope or record why they defer to CP2 · `specs/parser-check/research.md`
- [x] **T029** [US2] DECISION + research-correction: does the subprocess interpreter that runs generated modules (`handlers/execution.py`) support importing `flextoolsmcp.server.scan.*` directly? `handle_run_module` (execution.py:2685-4530) is one ~1800-line function where `code` is a **string**, ast-parsed in place, spliced into a literal template as `MODULE_CODE = {code}` (~4172), written to a temp file (4195) and run via `run_script_async` (4452) -- there is no reusable build-and-run(code_text, project_name, write_enabled) primitive, and the casting/preflight validators only ever run over caller-supplied `code` text. They cannot "cover" a module already living at `server/scan/grammar_scan_module.py` the way research D1 (research.md:126) claims. **If import works:** author a minimal new script template that imports the module normally and returns findings via `report.Result(...)`, read back through the `===FLEXTOOLS_USER_RESULT===` sentinel (execution.py:3869-3888 defines it, 4481-4490 reads it) -- the preferred path. **If it does not:** read the module file as text and reuse the existing splice path instead. Record the verdict and correct D1's "covered by the existing preflight/casting validators" claim, which is not achievable as scoped · `specs/parser-check/research.md`
- [x] **T027** [P] Correct SPEC 9.5.4 in place, four fixes: (1) row 8 -- rule ordering is `IPhSegmentRule.OrderNumber` grouped via `InitialStratumRA`/`FinalStratumRA`; `IMoStratum` has **no** rule collection, its only properties are `Abbreviation`, `Description`, `Name`, `PhonemesRA`; (2) the implementation note at SPEC.md:1416 ("Only rows 2, 4 and 9 have had their LCM property names verified") is now stale in the *opposite* direction -- rows 1, 2, 3-epenthesis, 4, 6, 8-corrected, 9 and 10 are verified; only row 3's metathesis half, row 5, and row 7's `AlternateFormsOS` half remain outstanding (exactly T016's targets); (3) add the `OrderNumber` caveat: each rule references exactly one `InitialStratumRA`/`FinalStratumRA` pair, so `OrderNumber` is comparable only **within** a stratum-pair grouping, and is very likely a per-pair counter, not a grammar-wide ordinal -- never sort or compare it across pairs; (4) SPEC 15's CP1 row promises an agent-probe "refusal" while CP1 actually ships tested refusal **logic** with no live caller -- reword to "refusal logic, shipped with tests; first live caller at CP2" · `specs/parser-check/SPEC.md`
- [x] **T033** [P] CP1 scan implementation table absorbing the per-row LCM predicates T019/T034/T035 point at: `cast_example` guidance (32 of 37 `IMoStemAllomorph` properties and 31 of 36 `IPhRegularRule` properties require a cast), the emptiness predicate `form in (None, "", "***")` (CLAUDE.md's Flexicon Operations-layer `"***"` -> `""` normalization does **not** apply on this direct-LCM-read path), the `OrderNumber` stratum-pair-only comparability caveat, the gated sub-checks and their `checks_skipped` fallback, and this note: `Disabled`/`OrderNumber`/`InitialStratumRA`/`FinalStratumRA` are declared **once** on the base `IPhSegmentRule` and are **not** redeclared in `IPhRegularRule`'s or `IPhMetathesisRule`'s own `properties` array in the index -- inheritance makes them reachable, but `flextools_get_object_api` on the derived interface will not show them · `specs/parser-check/data-model.md`

**⟶ Wait for the `T016` -> `T031` -> `T029` chain to finish (`T027`/`T033` need not be done), then:**

**Wave 3 -- independent (different files):**

- [x] **T017** [P] [US2] `GrammarHealthInput`: `project_name` (str or null, falls back to `session_state.project_name`), `checks` (list[str] or null), `limit` (int, default 20); plus `GrammarHealthFinding`, the closed output model -- `model_config = ConfigDict(extra="forbid")` and an explicit six-key field set (`check_id, spec_row, count, measured, evidence_basis, objects`), which is what T014's allowlist test asserts against -- structural closure, not just name-denial. **`objects[]` items need their own closed model**, `FoundObject` per [`data-model.md`](./data-model.md): `extra="forbid"` with exactly `hvo, class_name, label, goto_url`. Phase 4's independent test expects `goto_url`s, which can only live on an item model, and T014 polices "no severity proxy at any nesting level" -- an open item model would leave that nesting level unclosed · `src/flextoolsmcp/server/models.py`
- [x] **T018** [P] [US2] Register the `flextools_grammar_health` tool definition, annotated `READ_ONLY_SAFE` · `src/flextoolsmcp/server/tool_definitions.py`
- [x] **T030** [P] [US2] Build the subprocess seam T029 chose. Do **not** refactor `handle_run_module` unless T029's verdict forces it · `src/flextoolsmcp/server/handlers/execution.py`
- [x] **T019** [P] [US2] Phonology rows 2, 4, 9 -- all three LCM names already verified, none gated by T016 -- using `IPhPhoneme.CodesOS` (row 2), `IPhIterationContext.Maximum == -1` (row 4), `IPhPhoneme.FeaturesOA` (row 9); per-row predicates and cast guidance per `data-model.md` (T033). Each finding carries `check_id`, `spec_row`, `count`, `measured`, `evidence_basis` and capped `objects[]`; no severity field of any kind. **Returns findings via `report.Result(...)`**, per T029's chosen subprocess seam. Ships first -- no T016 gate, no dependency beyond T017/T018 · `src/flextoolsmcp/server/scan/grammar_scan_module.py`

**⟶ Wait for Wave 3 to finish (same file as T019), then:**

- [x] **T034** [US2] Morphology rows 1, 6, 7, 10, added to the same module. Row 1: `IMoForm.Form` emptiness via `form in (None, "", "***")` (T033) -- counts every zero-surface `IMoForm` **unconditionally**, not position-conditioned by optional-slot reachability (that walk -- slot -> `Affixes` -> MSA -> owning entry -> `AlternateFormsOS` -- is deferred; the allomorph -> owning-entry hop is a known flexicon read gap already tasked flexicon-first under S9; `measured`/`evidence_basis` wording must not claim slot-conditioning until that lands). Row 6: `IMoForm.IsComplete` (research D4's predicate). Row 10: `IMoInflAffixSlot.Optional`/`.Affixes` (`IMoInflAffixSlot` is **not** `ICmPossibility`). Row 7 is **two** independently-gateable sub-checks: `IMoStemAllomorph.StemNameRA` (kind `RA` -> `IMoStemName`, already verified -- written now, ungated) and `ILexEntry.AlternateFormsOS.Count > 1` (per T016's verdict: written check on confirmation, `checks_skipped` entry with reason `lcm_name_unverified` otherwise). Same `report.Result(...)` return channel as T019 · `src/flextoolsmcp/server/scan/grammar_scan_module.py`

**⟶ Wait for T034 (same file), then:**

- [ ] **T035** [US2] Rule-ordering rows 3, 5, 8, added to the same module. Row 3's epenthesis half (`IPhRegularRule` with empty `StrucDescOS`) is ungated; its metathesis half (`IPhMetathesisRule`) and row 5 (affix-process rule count x (`IPhRegularRule` + `IPhMetathesisRule`) count) are gated on T016's verdict, same written-or-`checks_skipped` branching. Row 8 in its corrected form: ordering lives on `IPhSegmentRule.OrderNumber`, grouped via `InitialStratumRA`/`FinalStratumRA`, never a collection on `IMoStratum`; `OrderNumber` is comparable only within one stratum-pair grouping (T033), never sorted or compared across pairs. `IPhSegmentRule.Disabled` gates every rule-based check in this task. Same `report.Result(...)` return channel as T019/T034 · `src/flextoolsmcp/server/scan/grammar_scan_module.py`

**⟶ Wait for T035 (same file), then:**

- [ ] **T020** [US2] Handler: runs the scan through the subprocess seam T029 decided and T030 built -- the MCP server process never opens a FieldWorks project -- and assembles `checks_run`, `checks_skipped`, `findings` and `next_step: null`, capping `objects[]` per check at `limit` (SPEC S7: responses summarise, never inline the full set). **Does not call `check_active_parser()`** -- it runs no parser and reads no engine-specific object. Reuses `project_not_found`, `project_locked`, `project_drive_unavailable`, `project_path_mismatch` unchanged · `src/flextoolsmcp/server/handlers/grammar_health.py`

**⟶ Wait for T020, then:**

- [ ] **T021** [US2] Route it: add `TOOL_GRAMMAR_HEALTH`, the dispatch entry, and the name to `ALL_TOOL_NAMES` · `src/flextoolsmcp/server/dispatch.py`

**Checkpoint.** US2 is independently functional and shippable on its own: the scan
runs on any openable project with no ParserCore, no `hc` tool and no parse involved.

---

## Phase 5: US3 -- refuse rather than mislead (P2)

**Goal.** The two refusals SPEC 3.2 and 12.7 demand, shipped with their tests at CP1.
Their first caller is a spine-executing handler, which arrives at CP2 -- so these are
correct-and-tested helpers here, deliberately not wired into a handler that does not
exist.

**Independent test.** Against a project fixture whose `ActiveParser` is `XAmple`,
`check_active_parser(project, supported_engines=("HC",))` refuses with
`parser_engine_mismatch` and no parse is attempted; against an `HC` project with no
HermitCrab agent, the probe returns `absent` and a `parser_agent_missing` payload
rather than letting `KeyNotFoundException` escape.

### Tests

**Wave 1 -- independent (different files):**

- [x] **T022** [P] [US3] Engine-gate tests: `ActiveParser == "XAmple"` raises `parser_engine_mismatch` with `configured_engine`, `supported_engines`, `hint`; accepted values are exactly `"XAmple"` and `"HC"`, **case-sensitive**; a corrupt `ParserParameters` XML **reads as XAmple and refuses** (fail-safe, never silently HC); `ActiveParser` is re-read live on every call and never cached per session -- it is user-flippable mid-session · `tests/test_parser_engine_gate.py`
- [x] **T023** [P] [US3] Agent-probe tests: with `ActiveParser == "HC"` and `kguidAgentHermitCrabParser` absent from `ICmAgentRepository`, the probe reports `absent` and produces `parser_agent_missing` with `agent_guid`, `agent_name: "HermitCrab"`, `active_engine`, `probe_source` and `hint` -- and **no `KeyNotFoundException` escapes**; the same fixture leaves the **read spine `ready`**, since `try_word` neither files nor resolves an agent; with no project open the state is `skipped`, which is never reported as a pass · `tests/test_parser_agent_probe.py`

### Implementation

**Wave 2 (single):**

- [x] **T024** [US3] `check_active_parser(project, supported_engines=("HC",))` -- intended as the **first statement** of each spine-executing handler (CP2 onward), before any `HCParser` or config-export construction. Live re-read, case-sensitive comparison, defaults to `"XAmple"` on any `ParserParameters` XML parse failure so a corrupt value refuses rather than silently proceeding as HC · `src/flextoolsmcp/server/parser_probe.py`

**⟶ Wait for T024 (same file), then:**

- [x] **T025** [US3] `AgentProbeState` (`present` | `absent` | `skipped`) and the HC-agent probe resolving `kguidAgentHermitCrabParser` from `ICmAgentRepository`, catching `KeyNotFoundException` and mapping it to `parser_agent_missing` with `probe_source` (`bootstrap_absent` | `lookup_failed`). Modelled separately from `ProbeResult` precisely so `skipped` can never be flattened into `ok=True`. Ships as a reusable function for CP2 callers; `flextools_health` continues to report `skipped` (research D2) · `src/flextoolsmcp/server/parser_probe.py`

**Checkpoint.** US3 is independently testable against fixtures; no handler calls it
yet, by design.

---

## Phase 6: Polish

**Wave 1:**

- [ ] **T026** [P] CP1 boundary regression, restated as two concrete, combinable checks (a single unfalsifiable "every code path" assertion is not a test): **(a) static** -- a grep/AST scan over `src/flextoolsmcp/server/**` asserting no literal `HCParser(` construction call exists anywhere, excluding `parser_probe.py`'s own `Assembly.LoadFile`/`GetMembers` reflection; **(b) dynamic** -- runs the full CP1 test suite with a spy/patch on the CLR construction point and asserts zero invocations. Static alone misses construction reached via computed strings or `getattr`; dynamic alone misses dead code the suite never exercises. Also asserts no grammar is loaded and no word is parsed, and that parseability is never derived from analysis or wordform counts (SPEC 3.1) · `tests/test_cp1_boundary.py`

**⟶ Wait for T026, then:**

- [ ] **T028** Validate against the Success Criteria: run the full test suite and the project's lint, confirming these CP1-scoped SPEC 16 groups all pass -- **Unit**: the error-envelope `extra="forbid"` bullet only (T006); **ParserCore capability probe (5.4)**, all four bullets (T007); **HC agent probe (12.7)**, all three bullets (T012, T023, T025); **G4 / grammar health (9.5)**, the "opens no parser / runs no parse" bullet, the "suspect, never a defect, no scalar score" bullet, and the "`next_step` never names a nonexistent tool" bullet (T014, T019/T034/T035, T026) -- **not** the conditional-proposal bullet, which defers to CP2; **Standing guarantees**, only "`ActiveParser` mismatch produces `parser_engine_mismatch`, never a parse" (T022) and "parseability is never derived from analysis counts" (T014, T026) -- **not** `HCParser_DoesNotLoadXCore` or the oracle-absent bullet, both CP2+; **Integration (Windows + FieldWorks, no `hc` tool)**, its one bullet (T008). All other SPEC 16 groups (flexicon facade, Proposal review, Concurrency, Job model, Live) are out of CP1 scope and excluded here · repository root

---

## Dependencies & Execution Order

**Phase order.** Setup (T001-T002) → Foundational (T003-T006) → US1
(T007-T013, T032) → US2 (T014-T021, T016/T031/T029, T027, T030, T033-T035) → US3
(T022-T025) → Polish (T026, T028). Foundational blocks every story: the four error
detail models (and the `AnyDetail` Union they now must join) and their contract rows
must exist before any handler emits a code.

**Story independence.** US2 shares no source file with US1 or US3 and can be built,
tested and shipped on its own -- including its cycle-6 additions: `T016`/`T031`/`T029`
(`research.md`), `T030` (`execution.py`) and `T033` (`data-model.md`) touch no
US1/US3 file. US1 and US3 both live in `parser_probe.py`, so they are strictly
ordered -- but US1 is complete without US3, because `flextools_health` always reports
`agent_probe: "skipped"` (research D2) and never needs the live probe; `active_engine`
rests on the same premise, now recorded by T032.

**Per-phase waves.**

| Phase | Waves |
|---|---|
| Setup | W1: T001, T002 (both `[P]`) -- nothing blocks them |
| Foundational | W1: T003, T004, T005 (`[P]`) → W2: T006 (needs the models from T003, including the `AnyDetail` extension) |
| US1 | W1 tests: T007, T008, T032 (`[P]`; T032 is a research write, not a test, but shares the wave -- different file, no dependency) → W2: T009 → W3: T010 → W4: T011 (T009-T011 all `parser_probe.py`, strictly ordered) → W5: T012 (needs T011 and T032) → W6: T013 (both `diagnostic_health.py`) |
| US2 | W1 tests: T014, T015 (`[P]`) → W2: `T016` → `T031` → `T029` (`research.md` chain, strictly ordered, none `[P]` relative to each other), with `T027` (`SPEC.md`) and `T033` (`data-model.md`) `[P]` alongside it → W3: T017, T018, T030, T019 (`[P]`; needs the W2 chain finished, not T027/T033) → W4: T034 (same file as T019, strictly after it) → W5: T035 (same file, strictly after T034) → W6: T020 (needs the scan module and the input model) → W7: T021 (needs the tool definition and the handler) |
| US3 | W1 tests: T022, T023 (`[P]`) → W2: T024 → W3: T025 (both `parser_probe.py`) |
| Polish | W1: T026 (restated as static+dynamic, one file) → W2: T028 (enumerated CP1-scoped SPEC 16 groups) |

**The ordering constraints the plan fixes.** The probe precedes its consumer
(T009-T011 before T012), the contract rows precede the code that emits them
(T003-T005 before T012, T020, T024 and T025), and the subprocess-bridge decision
precedes both its build and its first callers (T029 before T030, and before
T019/T034/T035, which must know how to call `report.Result(...)`).

**File-sharing invariant.** No `[P]`-tagged task pair shares a file anywhere in the
35 tasks. `T019`/`T034`/`T035` share `grammar_scan_module.py` but are never `[P]`
relative to each other -- strictly ordered. `T016`/`T031`/`T029` share `research.md`
for the same reason. `T032` writes `research.md` too and *is* `[P]`, which is safe
only because it lands a whole phase earlier (Phase 3 W1) and Phase 3 closes before
Phase 4 opens -- phase ordering, not wave ordering, is what separates it from the
`T016`/`T031`/`T029` chain. `T027` (`SPEC.md`), `T033` (`data-model.md`) and `T030`
(`execution.py`) each own a unique file and may be `[P]`.
